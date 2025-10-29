
from datetime import timedelta
from qbittensor.utils.Timer import Timer
from qbittensor.utils.request.RequestManager import RequestManager
from qbittensor.utils.telemetry.TelemetryService import TelemetryService
import qbittensor


class Heartbeat:
    
    def __init__(self, request_manager: RequestManager):
        request_manager = request_manager
        self.telemetry_service = TelemetryService(request_manager)
        self.timer = Timer(timeout=timedelta(minutes=5), run=self.send_version_info, run_on_start=True)
        
    def send_version_info(self) -> None:
        """Send version info to telemetry service"""
        version = self._get_version()
        self.telemetry_service.vali_record_heartbeat(version=version)
            
    def _get_version(self) -> str:
        """Read the version from the qbittensor package __init__.py file and return it"""
        return qbittensor.__version__
        
