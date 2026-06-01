import sys, logging, os
sys.stdout = open("proxy_log.txt", "w", encoding="utf-8")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stdout, force=True)
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from qwen2openai.server import run
run()
