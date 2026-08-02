#!/usr/bin/env python3
"""Launch Golden Nutrition AI.  Usage: python run.py [port]

Binds to 127.0.0.1 by default. For access from your phone, don't widen the
bind — keep it on localhost and put Tailscale in front with HTTPS:
    ./scripts/setup_remote_access.sh
(GNA_HOST overrides the bind address if you really need it.)
"""
import os
import sys

from app import create_app

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
    host = os.environ.get('GNA_HOST', '127.0.0.1')
    app = create_app()
    try:
        from waitress import serve
    except ImportError:
        # Dev fallback. threaded=True so a long AI call can't freeze the UI.
        app.run(host=host, port=port, debug=False, threaded=True)
    else:
        print(f' * Serving on http://{host}:{port} (waitress)')
        serve(app, host=host, port=port, threads=8)
