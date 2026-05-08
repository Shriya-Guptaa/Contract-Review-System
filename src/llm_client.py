import os
import time
import logging
import requests
from config.model_config import REMOTE_LLM_URL

# ---------------- LOGGING SETUP ----------------
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/llm_usage.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

class LLMClient:
    """
    Remote-only LLM Client for Contract Review.
    Routes all requests to Colab via Ngrok.
    """

    def __init__(self):
        logging.info("Initializing in REMOTE Colab mode.")
        print(f"🚀 Remote LLM engaged. Routing traffic to: {REMOTE_LLM_URL}")

    def _format_prompt(self, prompt: str, system_msg: str) -> str:
        """Wraps the prompt in Mistral Instruct format."""
        return f"[INST] {system_msg}\n\n{prompt} [/INST]"

    def generate(
        self,
        prompt: str,
        system_msg: str = "You are a Legal Analyst.",
        max_tokens: int = 512,
        temperature: float = 0.2,
        step_name: str = "General",
        stop_words: list = None,
        **kwargs
    ) -> str:
        """Generates text using remote Colab/ngrok API."""

        kwargs.setdefault("repeat_penalty", 1.0)

        stops = ["[/INST]", "</s>"]

        if stop_words:
            stops.extend(stop_words)

        try:
            start_time = time.time()

            formatted_input = self._format_prompt(prompt, system_msg)

            payload = {
                "prompt": formatted_input,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": stops
            }

            response = requests.post(
                REMOTE_LLM_URL,
                json=payload,
                timeout=120
            )

            response.raise_for_status()

            output_text = response.json().get("text", "").strip()

            duration = round(time.time() - start_time, 2)

            logging.info(
                f"SUCCESS | step={step_name} | temp={temperature} | time={duration}s"
            )

            return output_text

        except requests.exceptions.RequestException as e:
            logging.error(
                f"REMOTE API FAILURE | Make sure Colab and Ngrok are running! | error={str(e)}"
            )
            raise RuntimeError(f"Could not reach Colab: {str(e)}")

        except Exception as e:
            logging.error(
                f"FAILURE | step={step_name} | error={str(e)}"
            )
            raise RuntimeError(f"LLM Error: {str(e)}")

    def clear_cache(self):
        """No local cache exists in remote mode."""
        pass