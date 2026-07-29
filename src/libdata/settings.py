from contextlib import contextmanager
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.engine import create_engine
from pydantic import  Field
from pydantic_settings import  BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(
        env="DATABASE_URL",
        default="postgresql://postgres:llpzHyFdmOUxXJwkwnHzBjymASMvbyVA@hayabusa.proxy.rlwy.net:50508/railway"
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
            # Resilience for a remote DB (Railway over the internet):
            # - pool_pre_ping: check a pooled connection is alive before use and
            #   transparently replace dead/stale ones instead of raising a 500.
            # - pool_recycle: drop connections older than 30 min so we never reuse
            #   one the server already closed on its idle timeout.
            # - connect_timeout: fail fast on a network/DNS blip rather than hang.
            return create_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args={"connect_timeout": 10},
            )
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
