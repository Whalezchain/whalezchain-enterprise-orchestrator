from threading import Lock

from .engine import WhalezchainTestnetEngine

engine = WhalezchainTestnetEngine()
engine_lock = Lock()
