# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2026 qBitTensor Labs
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
from types import SimpleNamespace
from typing import Any, Callable, Optional

import bittensor as bt
from bittensor.wallet import Keypair, Wallet
from bittensor.keyfiles import Keyfile
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Logging (bt.logging was removed; SDK uses stdlib under "bittensor.*")
# ---------------------------------------------------------------------------

class _LoggingCompat:
    """Drop-in replacement for the old bt.logging facade."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("quantum")
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)
            self._logger.propagate = False

    def set_config(self, config: Any = None, **_: Any) -> None:
        level = logging.INFO
        try:
            debug = bool(getattr(config, "debug", False)) if config is not None else False
            trace = bool(getattr(config, "trace", False)) if config is not None else False
            if debug or trace:
                level = logging.DEBUG
        except Exception:
            pass
        self._logger.setLevel(level)
        logging.getLogger("bittensor").setLevel(level)

    def check_config(self, config: Any = None) -> None:
        return None

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--logging.debug", action="store_true", default=False)
        parser.add_argument("--logging.trace", action="store_true", default=False)
        parser.add_argument(
            "--logging.logging_dir",
            type=str,
            default=os.path.expanduser("~/.bittensor/miners"),
        )
        parser.add_argument("--logging.record_log", action="store_true", default=False)

    def register_primary_logger(self, name: str) -> None:
        # Events logger registration is a no-op beyond attaching the name.
        _ = name

    def set_warning(self) -> None:
        self._logger.setLevel(logging.WARNING)
        logging.getLogger("bittensor").setLevel(logging.WARNING)

    def _fmt(self, *args: Any) -> str:
        if not args:
            return ""
        if len(args) == 1:
            return str(args[0])
        # Old bt.logging.debug("label", value) style
        return " ".join(str(a) for a in args)

    def debug(self, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(self._fmt(*args), **{k: v for k, v in kwargs.items() if k in ("exc_info",)})

    def info(self, *args: Any, **kwargs: Any) -> None:
        self._logger.info(self._fmt(*args), **{k: v for k, v in kwargs.items() if k in ("exc_info",)})

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(self._fmt(*args), **{k: v for k, v in kwargs.items() if k in ("exc_info",)})

    def error(self, *args: Any, **kwargs: Any) -> None:
        self._logger.error(self._fmt(*args), **{k: v for k, v in kwargs.items() if k in ("exc_info",)})

    def success(self, *args: Any, **kwargs: Any) -> None:
        self._logger.info(self._fmt(*args), **{k: v for k, v in kwargs.items() if k in ("exc_info",)})

    def trace(self, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(self._fmt(*args), **{k: v for k, v in kwargs.items() if k in ("exc_info",)})


# ---------------------------------------------------------------------------
# Config (bt.Config + SDK add_args were removed)
# ---------------------------------------------------------------------------

def _ns_from_dict(d: dict) -> SimpleNamespace:
    out: dict[str, Any] = {}
    for k, v in d.items():
        out[k] = _ns_from_dict(v) if isinstance(v, dict) else v
    return SimpleNamespace(**out)


def _merge_ns(base: SimpleNamespace, override: Any) -> SimpleNamespace:
    base_dict = vars(base).copy()
    if override is None:
        return _ns_from_dict(base_dict)
    if isinstance(override, SimpleNamespace):
        odict = vars(override)
    elif isinstance(override, dict):
        odict = override
    else:
        odict = getattr(override, "__dict__", {}) or {}
    for k, v in odict.items():
        if k in base_dict and isinstance(base_dict[k], SimpleNamespace) and isinstance(v, (SimpleNamespace, dict)):
            base_dict[k] = _merge_ns(base_dict[k], v)
        else:
            base_dict[k] = v
    return _ns_from_dict(base_dict)


class Config(SimpleNamespace):
    """Hierarchical config with merge() for neuron constructors."""

    def merge(self, other: Any) -> "Config":
        merged = _merge_ns(self, other)
        # Re-wrap as Config
        cfg = Config(**vars(merged))
        return cfg

    def __call__(self) -> "Config":
        # Some template code treats config as callable.
        return self


def _set_nested(root: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = root
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def config_from_parser(parser: argparse.ArgumentParser, args: Optional[list[str]] = None) -> Config:
    """Parse CLI args into a hierarchical Config namespace."""
    known, _ = parser.parse_known_args(args=args)
    tree: dict[str, Any] = {}
    for key, value in vars(known).items():
        if "." in key:
            _set_nested(tree, key, value)
        else:
            tree[key] = value
    # Ensure common sections exist with defaults.
    tree.setdefault("wallet", {})
    tree["wallet"].setdefault("name", "default")
    tree["wallet"].setdefault("hotkey", "default")
    tree["wallet"].setdefault("path", os.path.expanduser("~/.bittensor/wallets"))
    tree.setdefault("subtensor", {})
    tree["subtensor"].setdefault("network", os.environ.get("BT_NETWORK", "finney"))
    tree["subtensor"].setdefault(
        "chain_endpoint",
        tree["subtensor"].get("network") or "finney",
    )
    tree.setdefault("logging", {})
    tree["logging"].setdefault("logging_dir", os.path.expanduser("~/.bittensor/miners"))
    tree["logging"].setdefault("debug", False)
    tree["logging"].setdefault("trace", False)
    tree.setdefault("axon", {})
    tree["axon"].setdefault("port", 8091)
    tree["axon"].setdefault("ip", "0.0.0.0")
    tree["axon"].setdefault("external_ip", None)
    tree["axon"].setdefault("external_port", None)
    tree.setdefault("neuron", {})
    tree.setdefault("blacklist", {})
    tree.setdefault("treasury", {})
    tree.setdefault("wandb", {})
    return Config(**vars(_ns_from_dict(tree)))


def wallet_add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wallet.name", type=str, default="default")
    parser.add_argument("--wallet.hotkey", type=str, default="default")
    parser.add_argument(
        "--wallet.path",
        type=str,
        default=os.path.expanduser("~/.bittensor/wallets"),
    )


def subtensor_add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--subtensor.network",
        type=str,
        default=os.environ.get("BT_NETWORK", "finney"),
        help="Network name (finney/test/local) or ws(s):// endpoint",
    )
    parser.add_argument(
        "--subtensor.chain_endpoint",
        type=str,
        default=None,
        help="Optional chain endpoint override (ws/wss URL)",
    )


def axon_add_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--axon.port", type=int, default=8091)
    parser.add_argument("--axon.ip", type=str, default="0.0.0.0")
    parser.add_argument("--axon.external_ip", type=str, default=None)
    parser.add_argument("--axon.external_port", type=int, default=None)


def _is_publishable_ip(ip: str | None) -> bool:
    """True if *ip* can be advertised on-chain as a peer destination."""
    value = (ip or "").strip()
    if not value:
        return False
    if value in {"0.0.0.0", "::", "localhost", "::1"}:
        return False
    if value.startswith("127."):
        return False
    return True


def detect_external_ip() -> str | None:
    """Best-effort outbound interface IP (not loopback).

    Used when ``--axon.external_ip`` is unset. Behind NAT this may be a
    private address; operators who need a public IP should set the flag.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("1.1.1.1", 80))
            ip = sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        return None
    return ip if _is_publishable_ip(ip) else None


def resolve_axon_external_ip(*candidates: str | None) -> str | None:
    """First publishable IP among *candidates*, else auto-detect."""
    for candidate in candidates:
        if _is_publishable_ip(candidate):
            return str(candidate).strip()
    return detect_external_ip()


# ---------------------------------------------------------------------------
# Synapse / terminal models (networking schema only; transport is local)
# ---------------------------------------------------------------------------

class TerminalInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    status_code: Optional[int] = None
    status_message: Optional[str] = None
    process_time: Optional[str] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    version: Optional[int] = None
    nonce: Optional[int] = None
    uuid: Optional[str] = None
    hotkey: Optional[str] = None
    signature: Optional[str] = None


class Synapse(BaseModel):
    """Minimal replacement for the removed bt.Synapse."""

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
        # Match old bt.Synapse behavior: coerce nested models on attribute set
        # (tests and handlers often assign plain dicts into typed fields).
        validate_assignment=True,
    )

    dendrite: Optional[TerminalInfo] = Field(default=None)
    axon: Optional[TerminalInfo] = Field(default=None)
    computed_body_hash: Optional[str] = None
    timeout: Optional[float] = 12.0

    def deserialize(self) -> "Synapse":
        return self

    def copy(self) -> "Synapse":
        return self.model_copy(deep=True)


class AxonInfo(BaseModel):
    """Endpoint info previously taken from metagraph.axons[uid]."""

    model_config = ConfigDict(extra="allow")

    ip: str = "0.0.0.0"
    port: int = 0
    ip_type: int = 4
    hotkey: str = ""
    coldkey: str = ""
    protocol: int = 4
    version: int = 0
    placeholder1: int = 0
    placeholder2: int = 0

    @property
    def is_serving(self) -> bool:
        ip = (self.ip or "").strip()
        if not ip or ip in ("0.0.0.0", "0.0.0.0.0", "0.0.0"):
            return False
        return bool(self.port and self.port != 0)

    @classmethod
    def from_endpoint(
        cls,
        endpoint: Optional[str],
        *,
        hotkey: str = "",
        coldkey: str = "",
    ) -> "AxonInfo":
        if not endpoint:
            return cls(hotkey=hotkey, coldkey=coldkey)
        # endpoint is "ip:port" (may be IPv6 with brackets — keep simple split)
        if endpoint.startswith("["):
            # [ipv6]:port
            try:
                host, port_s = endpoint.rsplit("]:", 1)
                host = host.lstrip("[")
                return cls(ip=host, port=int(port_s), hotkey=hotkey, coldkey=coldkey)
            except Exception:
                return cls(hotkey=hotkey, coldkey=coldkey)
        if ":" in endpoint:
            host, port_s = endpoint.rsplit(":", 1)
            try:
                return cls(ip=host, port=int(port_s), hotkey=hotkey, coldkey=coldkey)
            except Exception:
                return cls(ip=host, port=0, hotkey=hotkey, coldkey=coldkey)
        return cls(ip=endpoint, port=0, hotkey=hotkey, coldkey=coldkey)


# ---------------------------------------------------------------------------
# Metagraph adapter (old numpy-array surface → v11 typed metagraph)
# ---------------------------------------------------------------------------

class MetagraphAdapter:
    """Adapt v11 Metagraph to the attributes the neuron template still expects."""

    def __init__(self, metagraph: Any, *, netuid: int, subtensor: Any = None):
        self._mg = metagraph
        self.netuid = netuid
        self.subtensor = subtensor
        self.network = getattr(subtensor, "network", None)
        self._rebuild()

    def _rebuild(self) -> None:
        import numpy as np

        neurons = list(getattr(self._mg, "neurons", None) or list(self._mg))
        self.neurons = neurons
        self.hotkeys = [n.hotkey for n in neurons]
        self.coldkeys = [n.coldkey for n in neurons]
        self.n = len(neurons)
        self.uids = np.array([int(n.uid) for n in neurons], dtype=np.int64)
        stakes = []
        for n in neurons:
            stake = getattr(n, "total_stake", None) or getattr(n, "stake", None)
            value = 0.0
            if stake is not None:
                for attr in ("alpha", "amount", "tao"):
                    if not hasattr(stake, attr):
                        continue
                    try:
                        value = float(getattr(stake, attr))
                        break
                    except Exception:
                        continue
                else:
                    try:
                        value = float(stake)
                    except Exception:
                        value = 0.0
            stakes.append(value)
        self.S = np.array(stakes, dtype=np.float64)
        self.validator_permit = [bool(getattr(n, "validator_permit", False)) for n in neurons]
        self.last_update = [int(getattr(n, "last_update", 0) or 0) for n in neurons]
        self.axons = [
            AxonInfo.from_endpoint(
                getattr(n, "axon", None),
                hotkey=n.hotkey,
                coldkey=n.coldkey,
            )
            for n in neurons
        ]
        self.block = getattr(self._mg, "block", 0)
        self.num_uids = getattr(self._mg, "num_uids", self.n)
        self.owner_hotkey = getattr(self._mg, "owner_hotkey", None)
        self.owner_coldkey = getattr(self._mg, "owner_coldkey", None)
        self.raw = self._mg

    def sync(self, subtensor: Any = None, lite: bool = True, block: Optional[int] = None) -> "MetagraphAdapter":
        sub = subtensor or self.subtensor
        if sub is None:
            raise RuntimeError("Cannot sync metagraph without a subtensor client")
        self.subtensor = sub
        kwargs = {"netuid": self.netuid}
        if block is not None:
            kwargs["block"] = block
        self._mg = sub.subnets.metagraph(**kwargs)
        self._rebuild()
        return self

    def neuron(self, uid: int) -> Any:
        return self._mg.neuron(uid)

    def by_hotkey(self, hotkey: str) -> Any:
        return self._mg.by_hotkey(hotkey)

    def __len__(self) -> int:
        return self.n

    def __iter__(self):
        return iter(self.neurons)

    def __repr__(self) -> str:
        return f"MetagraphAdapter(netuid={self.netuid}, n={self.n}, block={self.block})"


# ---------------------------------------------------------------------------
# Axon / Dendrite (minimal HTTP transport using bittensor.http_auth)
# ---------------------------------------------------------------------------

class Axon:
    """Serve a forward handler over HTTP with hotkey auth (v11 replacement)."""

    def __init__(self, wallet: Any = None, config: Any = None, port: int = 8091, ip: str = "0.0.0.0", **_: Any):
        self.wallet = wallet
        self.config = config
        self.port = port
        self.ip = ip
        self.forward_fn: Optional[Callable] = None
        self.blacklist_fn: Optional[Callable] = None
        self.priority_fn: Optional[Callable] = None
        self._server = None
        self._thread = None
        self.external_ip = None
        self.external_port = None
        if config is not None:
            axon_cfg = getattr(config, "axon", None)
            if axon_cfg is not None:
                self.port = int(getattr(axon_cfg, "port", self.port) or self.port)
                self.ip = str(getattr(axon_cfg, "ip", self.ip) or self.ip)
                cfg_ext_ip = getattr(axon_cfg, "external_ip", None)
                if _is_publishable_ip(cfg_ext_ip):
                    self.external_ip = str(cfg_ext_ip).strip()
                cfg_ext_port = getattr(axon_cfg, "external_port", None)
                if cfg_ext_port:
                    self.external_port = int(cfg_ext_port)

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        axon_add_args(parser)

    def attach(
        self,
        forward_fn: Callable,
        blacklist_fn: Optional[Callable] = None,
        priority_fn: Optional[Callable] = None,
    ) -> "Axon":
        self.forward_fn = forward_fn
        self.blacklist_fn = blacklist_fn
        self.priority_fn = priority_fn
        return self

    def serve(self, netuid: int, subtensor: Any = None) -> "Axon":
        """Publish ip:port on-chain via ServeAxon.

        Raises if there is no wallet, subtensor, or publishable IP. A chain
        ServeAxon failure (already served, Custom error 11, etc.) logs a
        warning and still starts the local axon using the last on-chain record.
        """
        if subtensor is None or self.wallet is None:
            raise RuntimeError("Axon.serve requires a wallet and subtensor")

        cfg_ip = getattr(getattr(self.config, "axon", None), "external_ip", None)
        ip = resolve_axon_external_ip(self.external_ip, cfg_ip)
        if not ip:
            raise RuntimeError(
                "Axon.serve: no publishable IP. Set --axon.external_ip to a "
                "non-loopback address peers can reach (127.0.0.1 is rejected on-chain)."
            )
        self.external_ip = ip
        port = (
            self.external_port
            or getattr(getattr(self.config, "axon", None), "external_port", None)
            or self.port
        )
        self.external_port = int(port)

        result = subtensor.execute(
            bt.ServeAxon(netuid=netuid, ip=str(ip), port=int(self.external_port)),
            self.wallet,
        )
        if hasattr(result, "success") and not result.success:
            bt.logging.warning(
                f"ServeAxon failed ({getattr(result, 'error', result)}); "
                f"starting local axon on {ip}:{self.external_port} using last on-chain record"
            )
            return self
        bt.logging.info(f"ServeAxon published {ip}:{self.external_port} on netuid {netuid}")
        return self

    def start(self) -> "Axon":
        """Start a lightweight FastAPI server in a background thread."""
        if self.forward_fn is None:
            raise RuntimeError("Axon.forward_fn not attached")
        try:
            import asyncio
            import uvicorn
            from fastapi import FastAPI, Request, HTTPException
        except ImportError as e:
            bt.logging.error(f"Axon.start requires fastapi+uvicorn: {e}")
            return self

        app = FastAPI()
        wallet = self.wallet
        forward_fn = self.forward_fn
        blacklist_fn = self.blacklist_fn
        my_hotkey = wallet.hotkey.ss58_address if wallet is not None else None

        # Register after definition. Postponed annotations make FastAPI treat
        # `request` as a query param and every POST returns 422.
        async def handle_synapse(request: Request):
            body = await request.body()
            target = request.scope.get("raw_path", b"/synapse").decode()
            if request.scope.get("query_string"):
                target += "?" + request.scope["query_string"].decode()
            caller_hotkey = None
            try:
                if my_hotkey:
                    caller = bt.http_auth.verify(
                        request.headers,
                        body,
                        method=request.method,
                        path=target,
                        self_hotkey_ss58=my_hotkey,
                    )
                    caller_hotkey = caller.hotkey_ss58
            except Exception as e:
                raise HTTPException(status_code=401, detail=str(e)) from e

            # request.body() already consumed the stream; parse from bytes.
            import json as _json

            payload = _json.loads(body.decode("utf-8") or "{}")
            # Resolve a postponed "Synapse" annotation to the class.
            raw_syn = getattr(forward_fn, "__annotations__", {}).get("synapse", Synapse)
            if isinstance(raw_syn, type) and issubclass(raw_syn, BaseModel):
                synapse_cls = raw_syn
            elif isinstance(raw_syn, str):
                resolved = getattr(getattr(forward_fn, "__globals__", {}), raw_syn, None)
                synapse_cls = (
                    resolved
                    if isinstance(resolved, type) and issubclass(resolved, BaseModel)
                    else Synapse
                )
            else:
                synapse_cls = Synapse
            synapse = synapse_cls.model_validate(payload)
            if synapse.dendrite is None:
                synapse.dendrite = TerminalInfo()
            synapse.dendrite.hotkey = caller_hotkey

            if blacklist_fn is not None:
                try:
                    result = blacklist_fn(synapse)
                    if asyncio.iscoroutine(result):
                        result = await result
                    blacklisted = result[0] if isinstance(result, (tuple, list)) else bool(result)
                    if blacklisted:
                        raise HTTPException(status_code=403, detail="blacklisted")
                except HTTPException:
                    raise
                except Exception as e:
                    bt.logging.warning(f"blacklist_fn error: {e}")
                    raise HTTPException(status_code=403, detail="blacklisted") from e

            result = forward_fn(synapse)
            if asyncio.iscoroutine(result):
                result = await result
            if hasattr(result, "model_dump"):
                return result.model_dump()
            return result

        handle_synapse.__annotations__["request"] = Request
        app.post("/synapse")(handle_synapse)

        config = uvicorn.Config(app, host=self.ip, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

        import threading

        def _run():
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        bt.logging.info(f"Axon HTTP server started on {self.ip}:{self.port}")
        return self

    def stop(self) -> "Axon":
        if self._server is not None:
            self._server.should_exit = True
        return self

    def __str__(self) -> str:
        hk = getattr(getattr(self.wallet, "hotkey", None), "ss58_address", "?")
        return f"Axon(hotkey={hk}, ip={self.ip}, port={self.port})"

    def __repr__(self) -> str:
        return self.__str__()


class Dendrite:
    """Query remote axons over HTTP with hotkey auth (v11 replacement)."""

    def __init__(self, wallet: Any = None, **_: Any):
        self.wallet = wallet
        self.keypair = getattr(wallet, "hotkey", None) if wallet is not None else None
        self._session = None

    async def aclose_session(self) -> None:
        if self._session is not None:
            try:
                await self._session.aclose()
            except Exception:
                pass
            self._session = None

    async def forward(
        self,
        axons: Any,
        synapse: Any = None,
        timeout: float = 12,
        deserialize: bool = True,
        run_async: bool = True,
        streaming: bool = False,
    ):
        if streaming:
            raise NotImplementedError("Streaming not implemented")
        import httpx

        if synapse is None:
            synapse = Synapse()

        single = not isinstance(axons, (list, tuple))
        axon_list = [axons] if single else list(axons)

        async def _one(axon: Any):
            ip = getattr(axon, "ip", None)
            port = getattr(axon, "port", None)
            receiver = getattr(axon, "hotkey", None) or ""
            if not ip or not port:
                s = synapse.copy() if hasattr(synapse, "copy") else synapse
                if getattr(s, "dendrite", None) is None:
                    s.dendrite = TerminalInfo()
                s.dendrite.status_code = 400
                s.dendrite.status_message = "invalid axon"
                return s.deserialize() if deserialize and hasattr(s, "deserialize") else s

            url = f"http://{ip}:{port}/synapse"
            body_obj = synapse.model_dump() if hasattr(synapse, "model_dump") else dict(synapse)
            import json

            body = json.dumps(body_obj, default=str).encode("utf-8")
            headers = {}
            if self.wallet is not None and receiver:
                try:
                    headers = bt.http_auth.sign(
                        self.wallet,
                        method="POST",
                        path="/synapse",
                        body=body,
                        receiver_ss58=receiver,
                    )
                except Exception as e:
                    bt.logging.debug(f"http_auth.sign failed: {e}")

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, content=body, headers=headers)
                s = synapse.copy() if hasattr(synapse, "copy") else synapse
                if resp.status_code == 200:
                    data = resp.json()
                    if hasattr(s, "model_validate"):
                        s = type(synapse).model_validate({**body_obj, **data})
                    if s.dendrite is None:
                        s.dendrite = TerminalInfo()
                    s.dendrite.status_code = 200
                    s.dendrite.status_message = "OK"
                else:
                    if s.dendrite is None:
                        s.dendrite = TerminalInfo()
                    s.dendrite.status_code = resp.status_code
                    s.dendrite.status_message = resp.text[:200]
                return s.deserialize() if deserialize and hasattr(s, "deserialize") else s
            except Exception as e:
                s = synapse.copy() if hasattr(synapse, "copy") else synapse
                if getattr(s, "dendrite", None) is None:
                    s.dendrite = TerminalInfo()
                s.dendrite.status_code = 408
                s.dendrite.status_message = str(e)
                return s.deserialize() if deserialize and hasattr(s, "deserialize") else s

        import asyncio

        results = await asyncio.gather(*(_one(a) for a in axon_list))
        return results[0] if single else list(results)

    def query(self, axons: Any, synapse: Any = None, timeout: float = 12, deserialize: bool = True, **kwargs: Any):
        """Sync wrapper used by SN48 validator forward."""
        import asyncio

        return asyncio.run(
            self.forward(
                axons=axons,
                synapse=synapse,
                timeout=timeout,
                deserialize=deserialize,
            )
        )

    def __str__(self) -> str:
        addr = getattr(self.keypair, "ss58_address", "?")
        return f"Dendrite({addr})"


# ---------------------------------------------------------------------------
# Install shims onto the bittensor package
# ---------------------------------------------------------------------------

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    logging_compat = _LoggingCompat()
    bt.logging = logging_compat  # type: ignore[attr-defined]
    bt.Config = Config  # type: ignore[attr-defined]
    bt.Synapse = Synapse  # type: ignore[attr-defined]
    bt.Axon = Axon  # type: ignore[attr-defined]
    bt.Dendrite = Dendrite  # type: ignore[attr-defined]
    bt.AxonInfo = AxonInfo  # type: ignore[attr-defined]
    bt.Keypair = Keypair  # type: ignore[attr-defined]
    bt.Keyfile = Keyfile  # type: ignore[attr-defined]
    # Wallet remains the real v11 Wallet; config-based construction is handled
    # by BaseNeuron. Keep a MockWallet alias for mock mode tests.
    if not hasattr(bt, "MockWallet"):
        bt.MockWallet = Wallet  # type: ignore[attr-defined]
    if not hasattr(bt, "MockSubtensor"):
        bt.MockSubtensor = object  # type: ignore[attr-defined]

    # Convenience: Wallet/Subtensor add_args used by config()
    Wallet.add_args = staticmethod(wallet_add_args)  # type: ignore[attr-defined]
    bt.Subtensor.add_args = staticmethod(subtensor_add_args)  # type: ignore[attr-defined]
    bt.Axon.add_args = classmethod(lambda cls, parser: axon_add_args(parser))  # type: ignore[attr-defined]

    _INSTALLED = True


install()
