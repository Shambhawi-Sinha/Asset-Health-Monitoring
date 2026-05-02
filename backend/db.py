"""
db.py — Oracle Autonomous Database connection
 
Uses mTLS wallet authentication. Wallet files (ewallet.pem, tnsnames.ora,
sqlnet.ora) must be present in the directory specified by OCI_WALLET_DIR.
 
On OCI Compute: OCI Resource Principal is used for authentication.
Outside OCI (e.g. dev VM): set OCI_DB_USERNAME / OCI_DB_PASSWORD explicitly.
 
Known issue — corporate VM DNS:
    Oracle ADB hostnames (e.g. adb.us-phoenix-1.oraclecloud.com) may fail to
    resolve on company-managed VMs. Fix: set DNS to 8.8.8.8 and flush cache.
    Verify connectivity:  Test-NetConnection -ComputerName <host> -Port 1522
"""
 
import os
from typing import List, Dict, Optional
import oracledb
 
WALLET_DIR = os.getenv("OCI_WALLET_DIR", "./wallet")
DB_USER    = os.getenv("OCI_DB_USERNAME")
DB_PASS    = os.getenv("OCI_DB_PASSWORD")
DB_DSN     = os.getenv("OCI_DB_DSN")
 
 
def get_connection() -> oracledb.Connection:
    """
    Return an Oracle ADB connection using mTLS wallet.
 
    oracledb thin mode does not require Oracle Instant Client.
    The wallet directory must contain:
        - ewallet.pem   (SSL certificate)
        - tnsnames.ora  (connection descriptor)
        - sqlnet.ora    (wallet location pointer)
    """
    return oracledb.connect(
        user=DB_USER,
        password=DB_PASS,
        dsn=DB_DSN,
        wallet_location=WALLET_DIR,
        wallet_password=os.getenv("OCI_WALLET_PASSWORD"),
    )
 
 
def query_to_dicts(sql: str, params: Optional[Dict] = None) -> List[Dict]:
    """Execute a SQL query and return rows as a list of dicts."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            cols = [col[0].upper() for col in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
 

