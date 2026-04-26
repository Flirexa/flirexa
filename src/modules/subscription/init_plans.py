"""
Initialize default subscription plans
Run this once after database migration
"""

from sqlalchemy.orm import Session
from src.database.connection import SessionLocal
from src.modules.subscription.subscription_manager import SubscriptionManager
from loguru import logger


def init_default_plans(db: Session):
    """Create default subscription plans"""
    manager = SubscriptionManager(db)

    try:
        manager.create_default_plans()
        logger.info("✅ Default subscription plans created")
    except Exception as e:
        logger.error(f"❌ Failed to create plans: {e}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        init_default_plans(db)
    finally:
        db.close()
