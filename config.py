"""项目配置"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
DB_PATH = os.path.join(DATA_DIR, "vt_circulars.json")

# GCN 接口
GCN_BASE = "https://gcn.nasa.gov"
GCN_ARCHIVE_URL = GCN_BASE + "/circulars/archive.json.tar.gz"  # 完整归档（每日更新一次）
GCN_CIRC_URL = GCN_BASE + "/circulars/{cid}.json"              # 单条 by circularId

# 抓取参数
UPDATE_INTERVAL_SECONDS = 600        # 10 分钟
HTTP_TIMEOUT = 30
HTTP_RETRY = 3
HTTP_SLEEP_BETWEEN = 0.3             # 礼貌限速
USER_AGENT = "VT-GCN-History/1.0 (research)"

# 过滤关键词（标题中包含 SVOM/VT 或 VT 视为 VT 相关）
VT_KEYWORDS = ("SVOM/VT", "SVOM VT", " VT ")
# 额外的上限/探测关键词（用于辅助分类，不作为标题过滤）
UPPER_LIMIT_TOKENS = ("upper limit", "upper-limit", "non-detection", "no credible", "no optical counterpart", "not detected")
DETECTION_TOKENS = ("detection", "detected", "counterpart candidate", "afterglow", "counterpart", "discovery", "identified")

# Web 服务
HOST = "127.0.0.1"
PORT = 5050  # 避开 macOS AirPlay Receiver 默认占用的 5000 端口
DEBUG = False

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
