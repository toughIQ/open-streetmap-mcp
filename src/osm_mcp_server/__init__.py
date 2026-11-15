from . import server


def _quiet_cancel():
    """Do not answer cancelled requests.

    The MCP spec says a cancelled request gets no response, but the python SDK still sends a
    "Request cancelled" error. opencode forgets the request id on cancel, treats the late reply
    as a fatal "unknown message ID" transport error and drops the whole server.
    """
    from mcp.shared.session import RequestResponder

    async def cancel(self):
        self._cancel_scope.cancel()
        self._completed = True

    if hasattr(RequestResponder, "cancel"):
        RequestResponder.cancel = cancel


def main():
    """Main entry point for the package."""
    _quiet_cancel()
    server.mcp.run()

# Optionally expose other important items at package level
__all__ = ['main', 'server']
