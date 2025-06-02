from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "user"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    email = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    clients = relationship("Client", back_populates="user")
    reports = relationship("Report", back_populates="creator")

class Client(Base):
    __tablename__ = "client"

    client_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"))
    client_name = Column(String(100))

    user = relationship("User", back_populates="clients")

class Report(Base):
    __tablename__ = "report"

    report_id = Column(Integer, primary_key=True, index=True)
    create_by = Column(Integer, ForeignKey("user.user_id"))
    report_type = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", back_populates="reports")

class MspReport(Base):
    __tablename__ = "msp_report"

    report_id = Column(Integer, ForeignKey("report.report_id"), primary_key=True)
    request_date = Column(DateTime)
    completed_date = Column(DateTime)
    client_name = Column(String(50))
    system_name = Column(String(50))
    target_env = Column(String(10))
    requester = Column(String(10))
    request_type = Column(String(20))
    request_content = Column(Text)
    purpose = Column(Text)
    manager = Column(String(10))
    status = Column(String(10))
    response = Column(Text)
    etc = Column(Text)

    report = relationship("Report")


class ErrorReport(Base):
    __tablename__ = "error_report"

    report_id = Column(Integer, ForeignKey("report.report_id"), primary_key=True)
    error_start_date = Column(DateTime)
    client_name = Column(String(50))
    system_name = Column(String(50))
    target_env = Column(String(10))
    target_component = Column(String(50))
    customer_impact = Column(Text)
    error_info = Column(Text)
    error_reason = Column(Text)
    action_taken = Column(Text)
    manager = Column(String(10))
    status = Column(String(10))
    error_end_date = Column(DateTime)
    etc = Column(Text)

    report = relationship("Report")



class LogReport(Base):
    __tablename__ = "log_report"

    report_id = Column(Integer, ForeignKey("report.report_id"), primary_key=True)
    log_date = Column(DateTime)
    client_name = Column(String(50))
    system_name = Column(String(50))
    target_env = Column(String(10))
    log_type = Column(String(20))
    content = Column(Text)
    action = Column(Text)
    manager = Column(String(10))
    status = Column(String(10))
    completed_date = Column(DateTime)
    summary = Column(Text)
    etc = Column(Text)

    report = relationship("Report")