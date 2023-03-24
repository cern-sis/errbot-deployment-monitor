import os

import kopf
import requests
from errbot import BotPlugin
from kubernetes import client, config

config.load_incluster_config()
v1 = client.AppsV1Api()


class Monitor(BotPlugin):
    @kopf.on.startup()
    def configure_kopf(self, settings: kopf.OperatorSettings, **_):
        print(settings)
        settings.posting.enabled = False

    def _prepare_message_for_deployment(
        self, replicas_unavailable, deployment, **kwargs
    ):
        BOT_API_KEY = os.environ["BOT_K8S_KEY"]
        BOT_EMAIL = "k8s-alert-bot@cern-rcs-sis.zulipchat.com"
        namespace = kwargs["body"]["metadata"]["namespace"]
        if namespace not in os.environ.get("ACCEPTED_NAMESPACES", "").split(","):
            return
        deployment_name = deployment.metadata.name
        zulip_msg_content = f"""
                            :double_exclamation: Detected deployment
                            **{deployment_name}** is failing.\n
                            \n{replicas_unavailable} replica(s) is/are unavailable
                            """
        zulip_request_payload = {
            "type": "stream",
            "to": namespace.split("-")[0],
            "topic": namespace,
            "content": zulip_msg_content,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {BOT_EMAIL}:{BOT_API_KEY}",
        }

        response = requests.post(
            "https://cern-rcs-sis.zulipchat.com/api/v1/messages",
            json=zulip_request_payload,
            headers=headers,
        )

        self.log.info(response.status_code)

    def _prepare_message_for_container_restart(self, pod, container_name, **kwargs):
        BOT_API_KEY = os.environ["BOT_K8S_KEY"]
        BOT_EMAIL = "k8s-alert-bot@cern-rcs-sis.zulipchat.com"
        namespace = kwargs["body"]["metadata"]["namespace"]
        if namespace not in os.environ.get("ACCEPTED_NAMESPACES", "").split(","):
            return
        pod_name = pod.metadata.name
        zulip_msg_content = f"""
                            :warning: Detected container restarted
                            **{container_name}  has restarted in pod **{pod_name}**\n
                            """
        zulip_request_payload = {
            "type": "stream",
            "to": "test",
            "topic": "test",
            "content": zulip_msg_content,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {BOT_EMAIL}:{BOT_API_KEY}",
        }

        response = requests.post(
            "https://cern-rcs-sis.zulipchat.com/api/v1/messages",
            json=zulip_request_payload,
            headers=headers,
        )

        self.log.info(response.status_code)

    @kopf.on.event("v1", "pods")
    def container_restart_notification_handler(self, body, **kwargs):
        for container_status in body.status.container_statuses:
            if container_status.state.running and container_status.restart_count > 0:
                container = next(
                    (
                        c
                        for c in body.spec.containers
                        if c.name == container_status.name
                    ),
                    None,
                )
                if container:
                    self._prepare_message_for_container_restart(
                        body, container, **kwargs
                    )

    # send notification if the deployment is failing
    @kopf.on.field("apps", "v1", "deployments", field="status.replicas")
    def pod_phase_notification_handler(self, old, new, body, **kwargs):
        if not old:
            return
        deployment = v1.read_namespaced_deployment(
            name=body["metadata"]["name"], namespace=body["metadata"]["namespace"]
        )
        max_unavailable = deployment.spec.strategy.rolling_update.max_unavailable
        replicas_unavailable = old - new
        if replicas_unavailable > max_unavailable:
            self.prepare_message_for_deployment(
                replicas_unavailable, deployment, **kwargs
            )
