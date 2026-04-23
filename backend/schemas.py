from typing import Optional
from pydantic import BaseModel


class RegisterReq(BaseModel):
    username: str
    email: str
    password: str


class LoginReq(BaseModel):
    username: str
    password: str


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    email: str


class UserSettingsReq(BaseModel):
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_model: Optional[str] = None
    email_enabled: Optional[bool] = None
    email_smtp_host: Optional[str] = None
    email_smtp_port: Optional[int] = None
    email_sender: Optional[str] = None
    email_sender_pass: Optional[str] = None
    email_receiver: Optional[str] = None
    notify_min_confidence: Optional[float] = None
    initial_capital: Optional[float] = None


class UserSettingsResp(BaseModel):
    ai_api_key: str = ""
    ai_base_url: str = "https://yunwu.ai/v1"
    ai_model: str = "gpt-4o"
    email_enabled: bool = False
    email_smtp_host: str = "smtp.qq.com"
    email_smtp_port: int = 465
    email_sender: str = ""
    email_sender_pass: str = ""
    email_receiver: str = ""
    notify_min_confidence: float = 0.60
    initial_capital: float = 100000.0


class BuyReq(BaseModel):
    symbol: str
    name: str = ""
    shares: float
    price: float
    note: str = ""
    date: str = ""


class SellReq(BaseModel):
    symbol: str
    shares: float
    price: float
    note: str = ""
    date: str = ""
