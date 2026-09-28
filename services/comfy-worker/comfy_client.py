"""
comfy_client.py — ComfyUI REST API client

Handles:
  - Uploading input image to ComfyUI's input folder (direct filesystem copy)
  - Loading and patching workflow JSON
  - Submitting prompt to ComfyUI /prompt endpoint
  - Polling /history/{prompt_id} until done
  - Returning output file path
"""
import json
import logging
import shutil
import time
import uuid
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        input_dir: str,
        output_dir: str,
        poll_interval: float = 3.0,
        timeout: float = 600.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.poll_interval = poll_interval
        self.timeout = timeout

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _copy_input(self, src_path: Path, original_name: str) -> str:
        """
        Copy a local file into ComfyUI's input directory with a unique name.
        Returns the filename (not path) that ComfyUI uses to reference it.
        """
        ext = Path(original_name).suffix.lower() or ".jpg"
        unique_name = f"snapevent_{uuid.uuid4().hex}{ext}"
        dest = self.input_dir / unique_name
        shutil.copy2(src_path, dest)
        logger.debug(f"Copied input image to {dest}")
        return unique_name

    def _patch_workflow(self, workflow: dict, input_filename: str) -> dict:
        """
        Returns a copy of the workflow dict with the LoadImage node's image
        widget set to input_filename.

        The workflow JSON uses the LiteGraph format (list of nodes).
        We find the node with type=LoadImage and update widgets_values[0].
        """
        import copy
        patched = copy.deepcopy(workflow)

        nodes = patched.get("nodes", [])
        load_node = None
        for node in nodes:
            if node.get("type") == "LoadImage":
                load_node = node
                break

        if load_node is None:
            raise ValueError("No LoadImage node found in workflow JSON")

        # widgets_values[0] is the image filename
        if "widgets_values" in load_node:
            load_node["widgets_values"][0] = input_filename
        if "widgets_values_named" in load_node:
            load_node["widgets_values_named"]["image"] = input_filename

        return patched

    def _to_api_format(self, workflow: dict) -> dict:
        """
        Convert LiteGraph node-list format → ComfyUI API prompt format.
        ComfyUI /prompt expects: { "node_id": { "class_type": ..., "inputs": {...} }, ... }
        """
        nodes = workflow.get("nodes", [])
        links = workflow.get("links", [])

        # Build link lookup: link_id → (src_node_id, src_slot)
        link_map = {}
        for link in links:
            # link = [link_id, src_node_id, src_slot, dst_node_id, dst_slot, type]
            link_id = link[0]
            src_node_id = link[1]
            src_slot = link[2]
            link_map[link_id] = [str(src_node_id), src_slot]

        api_prompt = {}
        for node in nodes:
            node_id = str(node["id"])
            class_type = node.get("type", "")
            inputs = {}

            # Process widget inputs (non-linked values)
            widget_names = []
            if "inputs" in node:
                for inp in node["inputs"]:
                    name = inp["name"]
                    link_id = inp.get("link")
                    if link_id is not None:
                        # This input is connected via a link
                        inputs[name] = link_map[link_id]
                    # Widget-backed inputs are in widgets_values_named

            # Add widget values from widgets_values_named if present
            if "widgets_values_named" in node:
                for k, v in node["widgets_values_named"].items():
                    if k not in inputs:  # don't override linked inputs
                        inputs[k] = v
            elif "widgets_values" in node:
                # Fall back: match by order from node.inputs that have widgets
                widget_inputs = [
                    inp for inp in node.get("inputs", [])
                    if inp.get("link") is None and inp.get("widget")
                ]
                for i, wi in enumerate(widget_inputs):
                    if i < len(node["widgets_values"]):
                        inputs[wi["name"]] = node["widgets_values"][i]

            api_prompt[node_id] = {
                "class_type": class_type,
                "inputs": inputs,
            }

        return api_prompt

    def _submit_prompt(self, api_prompt: dict) -> str:
        """Submit prompt to ComfyUI and return prompt_id."""
        payload = {"prompt": api_prompt}
        resp = requests.post(f"{self.base_url}/prompt", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"ComfyUI rejected prompt: {data['error']}")
        if "node_errors" in data and data["node_errors"]:
            raise RuntimeError(f"ComfyUI node errors: {data['node_errors']}")

        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"No prompt_id in ComfyUI response: {data}")
        return prompt_id

    def _poll_history(self, prompt_id: str) -> dict:
        """
        Poll /history/{prompt_id} until the job is done.
        Returns the history item dict for this prompt.
        Raises TimeoutError if it takes longer than self.timeout seconds.
        """
        deadline = time.time() + self.timeout
        logger.info(f"Polling ComfyUI for prompt_id={prompt_id}")

        while time.time() < deadline:
            resp = requests.get(
                f"{self.base_url}/history/{prompt_id}", timeout=10
            )
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                item = history[prompt_id]
                status = item.get("status", {})
                if status.get("completed"):
                    logger.info(f"Prompt {prompt_id} completed")
                    return item
                if status.get("status_str") == "error":
                    msgs = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI execution error: {msgs}")

            time.sleep(self.poll_interval)

        raise TimeoutError(
            f"ComfyUI did not complete prompt {prompt_id} within {self.timeout}s"
        )

    def _get_output_paths(self, history_item: dict) -> list[Path]:
        """
        Extract output file paths from a completed history item.
        Looks for SaveImage node outputs.
        """
        outputs = history_item.get("outputs", {})
        paths = []
        for node_id, node_out in outputs.items():
            images = node_out.get("images", [])
            for img in images:
                filename = img.get("filename")
                subfolder = img.get("subfolder", "")
                img_type = img.get("type", "output")
                if img_type == "output" and filename:
                    if subfolder:
                        p = self.output_dir / subfolder / filename
                    else:
                        p = self.output_dir / filename
                    paths.append(p)
        return paths

    def _cleanup_input(self, filename: str) -> None:
        """Remove the temp input file after processing."""
        try:
            (self.input_dir / filename).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not clean up input file {filename}: {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def run_workflow(
        self,
        workflow_path: Path,
        image_path: Path,
        original_name: str,
    ) -> list[Path]:
        """
        Full pipeline for one image:
          1. Copy image to ComfyUI input dir
          2. Load + patch workflow JSON
          3. Convert to API format
          4. Submit to /prompt
          5. Poll /history until done
          6. Return list of output file Paths (usually one)
          7. Clean up input file

        Returns list of Path objects pointing to files in ComfyUI's output dir.
        """
        input_filename = self._copy_input(image_path, original_name)
        try:
            with open(workflow_path, "r") as f:
                workflow = json.load(f)

            patched = self._patch_workflow(workflow, input_filename)
            api_prompt = self._to_api_format(patched)

            logger.info(f"Submitting workflow {workflow_path.name} for image {original_name}")
            prompt_id = self._submit_prompt(api_prompt)

            history_item = self._poll_history(prompt_id)
            output_paths = self._get_output_paths(history_item)

            if not output_paths:
                raise RuntimeError(
                    f"ComfyUI returned no output images for prompt {prompt_id}"
                )

            logger.info(f"Got {len(output_paths)} output(s): {[str(p) for p in output_paths]}")
            return output_paths

        finally:
            self._cleanup_input(input_filename)
