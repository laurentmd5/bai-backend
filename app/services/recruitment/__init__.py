"""Recruitment and Candidate Screening module for Company Bot."""
from app.services.recruitment.cv_parser_service import cv_parser_service
from app.services.recruitment.recruiter_agent import recruiter_agent

__all__ = ["cv_parser_service", "recruiter_agent"]
