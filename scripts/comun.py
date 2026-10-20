import json
import os
import subprocess
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def cfg():
    with open(os.path.join(RAIZ, os.environ.get("TDPS_CONFIG", "config.json")), encoding="utf-8") as f:
        return json.load(f)


def ruta(*p):
    return os.path.join(RAIZ, *p)


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          errors="replace", check=True).stdout


def fin_dia(d):
    return f"{d} 23:59:59"


def inicio_dia_siguiente(d):
    import pandas as pd
    return (pd.Timestamp(d) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") + " 00:00:00"
