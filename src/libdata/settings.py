from contextlib import contextmanager
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.engine import create_engine
from pydantic import  Field
from pydantic_settings import  BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(
        env="DATABASE_URL",
        default="postgresql://postgres:demo123@localhost:5432/DBClaimCRM"
    )
    
    # Cloudinary Configuration
    cloudinary_cloud_name: str = Field(
        env="CLOUDINARY_CLOUD_NAME",
        default="dwdbsv8j8"
    )
    cloudinary_api_key: str = Field(
        env="CLOUDINARY_API_KEY",
        default="247181356229334"
    )
    cloudinary_api_secret: str = Field(
        env="CLOUDINARY_API_SECRET",
        default="kHEZYivWaxak7rid_WDD1FFSDWE"
    )

    def get_engine(self):
        try:
            assert self.database_url
            return create_engine(self.database_url)
        except AssertionError as a_error:
            print(a_error)
        return None

    @staticmethod
    def get_session(db_engine):
        return scoped_session(
            sessionmaker(autocommit=False, autoflush=True, bind=db_engine)
        )


settings = Settings()

engine = settings.get_engine()


@contextmanager
def get_session_ctx():
    db_session = Settings.get_session(db_engine=engine)
    db = db_session()
    print("Session created")
    try:
        yield db
        db.commit()  # Ensure the transaction is committed at the end
    except Exception as e:
        db.rollback()  # Rollback the transaction on error
        raise e
    finally:
        db.close()
        db_session.remove()
        print("Session closed and removed")


def get_session():
    with get_session_ctx() as db:
        yield db
