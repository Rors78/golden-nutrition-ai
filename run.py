#!/usr/bin/env python3
"""Launch Golden Nutrition AI.  Usage: python run.py [port]"""
import sys

from app import create_app

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
    create_app().run(host='127.0.0.1', port=port, debug=False)
