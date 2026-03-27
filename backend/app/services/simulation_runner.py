"""
SimulationRunner — spawns and manages the run_parallel_simulation.py subprocess.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("simulation_runner")

_SCRIPT = Path(__file__).parent.parent.parent / "simulations" / "run_parallel_simulation.py"
_PYTHON = sys.executable   # reuse the same venv python


class SimulationRunner:
    def __init__(self, config: type[Config] = Config):
        self.config = config
        self._procs: dict[str, subprocess.Popen] = {}

    def start(
        self,
        sim_id: str,
        entity_id: str,
        hypothetical_event: str | None = None,
    ) -> bool:
        sim_dir = Path(self.config.SIMULATIONS_DIR) / sim_id
        profiles_path = sim_dir / "profiles.json"
        config_path = sim_dir / "simulation_config.json"

        if not profiles_path.exists() or not config_path.exists():
            logger.error(f"Simulation {sim_id} missing profiles or config")
            return False

        cmd = [
            _PYTHON, str(_SCRIPT),
            "--simulation_id", sim_id,
            "--profiles_path", str(profiles_path),
            "--config_path", str(config_path),
            "--output_dir", str(sim_dir),
            "--entity_id", entity_id,
        ]
        if hypothetical_event:
            cmd += ["--hypothetical_event", hypothetical_event]

        # Pass environment (inherit current env which has .env loaded)
        import os
        env = os.environ.copy()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        self._procs[sim_id] = proc
        logger.info(f"Started simulation subprocess {sim_id} (pid={proc.pid})")

        # Stream logs in background thread
        def _stream():
            for line in proc.stdout:
                logger.info(f"[sim:{sim_id}] {line.rstrip()}")
            proc.wait()
            logger.info(f"[sim:{sim_id}] subprocess exited with code {proc.returncode}")

        threading.Thread(target=_stream, daemon=True, name=f"sim-log-{sim_id}").start()
        return True

    def stop(self, sim_id: str) -> bool:
        proc = self._procs.get(sim_id)
        if not proc:
            return False
        proc.terminate()
        logger.info(f"Terminated simulation {sim_id}")
        return True

    def is_running(self, sim_id: str) -> bool:
        proc = self._procs.get(sim_id)
        return proc is not None and proc.poll() is None


simulation_runner = SimulationRunner(Config)
