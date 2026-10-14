"""
Telemetria do PC para a tela: CPU (geral e por núcleo), RAM, disco, bateria, rede, I/O de disco, GPU NVIDIA,
ping e os processos que mais pesam. Tudo local, sem custo. Os itens caros (GPU, processos, ping) são medidos
em intervalos maiores e reaproveitados entre as amostras.
"""

import asyncio
import os
import shutil
import socket
import time

import psutil

_NOMES_IGNORADOS = {"System Idle Process", "Idle", "System"}


class Telemetria:
    def __init__(self):
        self._rede = psutil.net_io_counters()
        self._io = psutil.disk_io_counters()
        self._t = time.monotonic()
        self._gpu = None
        self._procs: list[dict] = []
        self._ping: float | None = None
        self._conhecidos: dict[int, psutil.Process] = {}
        self._ultimo_gpu = 0.0
        self._ultimo_procs = 0.0
        self._ultimo_ping = 0.0
        self._tem_nvidia = shutil.which("nvidia-smi") is not None
        self._nucleos = psutil.cpu_count(logical=True) or 1
        psutil.cpu_percent(interval=None, percpu=True)

    # ------------------------------------------------------------ itens caros
    def _ler_gpu(self):
        import subprocess
        try:
            saida = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            uso, temp, usada, total, nome = [x.strip() for x in saida.stdout.strip().split("\n")[0].split(",", 4)]
            return {"uso": float(uso), "temp": float(temp), "vram_usada": float(usada), "vram_total": float(total), "nome": nome}
        except Exception:
            return None

    def _ler_processos(self):
        atuais, lista = set(), []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pid = p.info["pid"]
                atuais.add(pid)
                proc = self._conhecidos.get(pid)
                if proc is None:
                    proc = self._conhecidos[pid] = p
                    proc.cpu_percent(None)       # a 1ª leitura é sempre 0; vale a partir da próxima
                    continue
                nome = p.info["name"] or "?"
                if nome in _NOMES_IGNORADOS:
                    continue
                cpu = proc.cpu_percent(None) / self._nucleos
                ram = proc.memory_info().rss / 1e6
                lista.append({"nome": nome.removesuffix(".exe")[:22], "cpu": round(cpu, 1), "ram_mb": round(ram)})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        for pid in list(self._conhecidos):
            if pid not in atuais:
                del self._conhecidos[pid]
        # junta processos do mesmo nome (o Chrome tem dezenas)
        somados: dict[str, dict] = {}
        for x in lista:
            s = somados.setdefault(x["nome"], {"nome": x["nome"], "cpu": 0.0, "ram_mb": 0})
            s["cpu"] = round(s["cpu"] + x["cpu"], 1)
            s["ram_mb"] += x["ram_mb"]
        return sorted(somados.values(), key=lambda x: (x["cpu"], x["ram_mb"]), reverse=True)[:5]

    @staticmethod
    def _medir_ping():
        t = time.perf_counter()
        try:
            with socket.create_connection(("1.1.1.1", 443), timeout=1.5):
                return round((time.perf_counter() - t) * 1000)
        except OSError:
            return None

    def _em_fundo(self, nome: str, funcao):
        async def tarefa():
            try:
                r = await asyncio.to_thread(funcao)
            except Exception:
                return
            if nome == "gpu":
                self._gpu = r
            elif nome == "procs":
                self._procs = r
            else:
                self._ping = r
        self._fundo = getattr(self, "_fundo", set())
        t = asyncio.create_task(tarefa())
        self._fundo.add(t)
        t.add_done_callback(self._fundo.discard)

    # ------------------------------------------------------------ amostra
    async def amostra(self) -> dict:
        agora = time.monotonic()
        dt = max(0.2, agora - self._t)
        rede, io = psutil.net_io_counters(), psutil.disk_io_counters()
        down = (rede.bytes_recv - self._rede.bytes_recv) / dt
        up = (rede.bytes_sent - self._rede.bytes_sent) / dt
        leitura = (io.read_bytes - self._io.read_bytes) / dt if io and self._io else 0
        escrita = (io.write_bytes - self._io.write_bytes) / dt if io and self._io else 0
        self._rede, self._io, self._t = rede, io, agora

        # Os itens caros rodam em segundo plano: a amostra devolve o último valor sem esperar.
        if self._tem_nvidia and agora - self._ultimo_gpu >= 2.5:
            self._ultimo_gpu = agora
            self._em_fundo("gpu", self._ler_gpu)
        if agora - self._ultimo_procs >= 3.5:
            self._ultimo_procs = agora
            self._em_fundo("procs", self._ler_processos)
        if agora - self._ultimo_ping >= 6:
            self._ultimo_ping = agora
            self._em_fundo("ping", self._medir_ping)

        bat = psutil.sensors_battery()
        nucleos = psutil.cpu_percent(interval=None, percpu=True)
        return {
            "tipo": "sistema",
            "cpu": round(sum(nucleos) / len(nucleos), 1) if nucleos else 0,
            "nucleos": [round(n) for n in nucleos],
            "ram": psutil.virtual_memory().percent,
            "disco": psutil.disk_usage(os.path.abspath(os.sep)).percent,
            "bateria": None if bat is None else {"pct": round(bat.percent), "tomada": bool(bat.power_plugged)},
            "rede": {"down": round(down), "up": round(up)},
            "disco_io": {"leitura": round(leitura), "escrita": round(escrita)},
            "gpu": self._gpu,
            "ping_ms": self._ping,
            "procs": self._procs,
            "uptime_s": int(time.time() - psutil.boot_time()),
        }
