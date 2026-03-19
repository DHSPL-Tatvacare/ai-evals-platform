"""Import all models so SQLAlchemy metadata knows about them."""
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User, UserRole, RefreshToken
from app.models.listing import Listing
from app.models.file_record import FileRecord
from app.models.prompt import Prompt
from app.models.schema import Schema
from app.models.evaluator import Evaluator
from app.models.chat import ChatSession, ChatMessage
from app.models.history import History
from app.models.setting import Setting
from app.models.tag import Tag
from app.models.job import Job
from app.models.eval_run import EvalRun, ThreadEvaluation, AdversarialEvaluation, ApiLog
from app.models.evaluation_analytics import EvaluationAnalytics
from app.models.invite_link import InviteLink
from app.models.tenant_config import TenantConfig

__all__ = [
    "Base",
    "Tenant", "TenantConfig", "User", "UserRole", "RefreshToken", "InviteLink",
    "Listing", "FileRecord", "Prompt", "Schema", "Evaluator",
    "ChatSession", "ChatMessage", "History", "Setting", "Tag",
    "Job", "EvalRun", "ThreadEvaluation", "AdversarialEvaluation", "ApiLog",
    "EvaluationAnalytics",
]
