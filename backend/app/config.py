import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

EC2_HOST = os.getenv("EC2_HOST", "15.135.200.112")
EC2_USER = os.getenv("EC2_USER", "ubuntu")
SSH_KEY_PATH = os.getenv(
    "SSH_KEY_PATH",
    r"D:\aws-keys\automated-server-monitoring-key.pem"
)
NAGIOS_STATUS_PATH = "/var/lib/nagios4/status.dat"
SSH_TIMEOUT_SECONDS = 20
