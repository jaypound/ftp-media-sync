"""
Host Verification Module
Ensures that only the backend host can trigger automatic video generation
"""
import os
import socket
import logging
import psycopg2
from typing import Dict, Any

logger = logging.getLogger(__name__)

class HostVerification:
    """Handle host verification for auto generation features"""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self._backend_host = None
        self._is_backend_cache = None
        
    def get_backend_host(self) -> str:
        """Get the configured backend host name"""
        if self._backend_host is None:
            # Try environment variable first
            self._backend_host = os.getenv('BACKEND_HOST', '').strip()
            
            # If not set, try to detect from database connection
            if not self._backend_host and self.db_manager:
                try:
                    # Get database host from connection
                    db_host = os.getenv('DB_HOST', 'localhost')
                    if db_host in ['localhost', '127.0.0.1', '::1']:
                        # Database is local, so this is the backend host
                        self._backend_host = socket.gethostname()
                except Exception as e:
                    logger.error(f"Error detecting backend host: {e}")
            
            # Default to mac-studio.local if nothing else works
            if not self._backend_host:
                self._backend_host = 'mac-studio.local'
                
        return self._backend_host
    
    def is_backend_host(self) -> bool:
        """Check if current machine is the backend host"""
        # Use cached result if available
        if self._is_backend_cache is not None:
            return self._is_backend_cache
            
        try:
            current_hostname = socket.gethostname()
            backend_hostname = self.get_backend_host()
            
            # Direct hostname match
            if current_hostname.lower() == backend_hostname.lower():
                self._is_backend_cache = True
                return True
            
            # Check for variations of mac-studio hostname
            # Handle cases like 'Jays-Mac-Studio.local' matching 'mac-studio.local'
            if 'mac-studio' in current_hostname.lower() and 'mac-studio' in backend_hostname.lower():
                self._is_backend_cache = True
                return True
            
            # Check if we can connect to local database (indicates backend host)
            if self.check_local_database_connection():
                self._is_backend_cache = True
                return True
                
            # Check IP addresses as fallback
            try:
                current_ips = set(self.get_all_ips())
                backend_ips = set(socket.gethostbyname_ex(backend_hostname)[2])
                if current_ips & backend_ips:  # Any intersection
                    self._is_backend_cache = True
                    return True
            except Exception as e:
                logger.debug(f"IP comparison failed: {e}")
            
            self._is_backend_cache = False
            return False
            
        except Exception as e:
            logger.error(f"Error checking if backend host: {e}")
            # Fail safe - don't run if we can't verify
            self._is_backend_cache = False
            return False
    
    def check_local_database_connection(self) -> bool:
        """Check if we can connect to database locally"""
        try:
            # Try to connect to database on localhost
            conn = psycopg2.connect(
                host='localhost',
                port=os.getenv('DB_PORT', '5432'),
                database=os.getenv('DB_NAME', 'ftp_sync'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', ''),
                connect_timeout=3
            )
            conn.close()
            return True
        except Exception:
            return False
            
    def get_all_ips(self) -> list:
        """Get all IP addresses for current machine"""
        ips = []
        try:
            hostname = socket.gethostname()
            ips.extend(socket.gethostbyname_ex(hostname)[2])
            
            # Also get IPs from network interfaces
            import netifaces
            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr:
                            ips.append(addr['addr'])
        except ImportError:
            # netifaces not available, use basic method
            pass
        except Exception as e:
            logger.debug(f"Error getting IPs: {e}")
            
        return list(set(ips))  # Remove duplicates
    
    def get_host_info(self) -> Dict[str, Any]:
        """Get detailed host information for debugging"""
        try:
            hostname = socket.gethostname()
            return {
                'current_hostname': hostname,
                'backend_hostname': self.get_backend_host(),
                'is_backend': self.is_backend_host(),
                'current_ips': self.get_all_ips(),
                'has_local_db': self.check_local_database_connection(),
                'env_backend_host': os.getenv('BACKEND_HOST', 'not set')
            }
        except Exception as e:
            logger.error(f"Error getting host info: {e}")
            return {
                'error': str(e),
                'is_backend': False
            }

# Singleton instance
_host_verifier = None

def get_host_verifier(db_manager=None) -> HostVerification:
    """Get or create the host verifier instance"""
    global _host_verifier
    if _host_verifier is None:
        _host_verifier = HostVerification(db_manager)
    elif db_manager and _host_verifier.db_manager is None:
        _host_verifier.db_manager = db_manager
    return _host_verifier

# Convenience functions
def is_backend_host() -> bool:
    """Check if current machine is the backend host"""
    return get_host_verifier().is_backend_host()

def get_host_info() -> Dict[str, Any]:
    """Get detailed host information"""
    return get_host_verifier().get_host_info()