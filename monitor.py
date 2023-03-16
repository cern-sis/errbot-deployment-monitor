import os

import kopf
import requests
from errbot import BotPlugin
from kubernetes import client, config

config.load_incluster_config()
v1 = client.AppsV1Api()


class Monitor(BotPlugin):
    @kopf.on.startup()
    def configure(self, settings: kopf.OperatorSettings, **_):
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
            _self.prepare_message_for_deployment(
                replicas_unavailable, deployment, **kwargs
            )
