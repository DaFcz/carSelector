"""Import every model so `Base.metadata` is fully populated - required for
Alembic autogenerate and for `Base.metadata.create_all()` to see all tables.
"""

from app.models.article import Article, ArticleRecipient, ArticleTranslation
from app.models.author_request import AuthorRequest
from app.models.brand import Brand
from app.models.car_model import CarModel
from app.models.color import Color
from app.models.comparison_view import ComparisonView, ComparisonViewModel
from app.models.configuration import Configuration
from app.models.configuration_color import ConfigurationColor
from app.models.feedback import Feedback
from app.models.liked_model import LikedModel
from app.models.login_code import LoginCode
from app.models.option_availability import OptionAvailability
from app.models.option_item import OptionItem
from app.models.powertrain import Powertrain
from app.models.price import Price
from app.models.saved_requirements import SavedRequirements
from app.models.shared_snapshot import SharedSnapshot
from app.models.source_document import SourceDocument
from app.models.trim import Trim
from app.models.user import User

__all__ = [
    "Article",
    "ArticleRecipient",
    "ArticleTranslation",
    "AuthorRequest",
    "Brand",
    "CarModel",
    "Color",
    "ComparisonView",
    "ComparisonViewModel",
    "Configuration",
    "ConfigurationColor",
    "Feedback",
    "LikedModel",
    "LoginCode",
    "OptionAvailability",
    "OptionItem",
    "Powertrain",
    "Price",
    "SavedRequirements",
    "SharedSnapshot",
    "SourceDocument",
    "Trim",
    "User",
]
