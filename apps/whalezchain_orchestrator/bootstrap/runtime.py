from __future__ import annotations


def initialize_runtime():

    # Import services to trigger execution registrations
    from ..services import execution_service

    return {
        "runtime": "initialized",
        "registrations": "loaded",
    }
