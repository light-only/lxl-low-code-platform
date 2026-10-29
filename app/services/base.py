from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """Thin base class for the business-logic (service) layer.

    Subclasses receive a database session and keep route handlers thin.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
