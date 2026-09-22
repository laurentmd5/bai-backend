"""
Email notification service for recruitment pipeline.
Handles white-label SMTP notifications to recruiter inbox upon candidate screening completion.
"""

import asyncio
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import smtplib
import ssl
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailNotificationService:
    """
    Asynchronous SMTP email service for sending recruitment notifications.
    Completely configurable and white-label via environment settings.
    """

    @property
    def host(self) -> str:
        return settings.SMTP_HOST

    @property
    def port(self) -> int:
        return settings.SMTP_PORT

    @property
    def user(self) -> Optional[str]:
        return settings.SMTP_USER

    @property
    def use_tls(self) -> bool:
        return settings.SMTP_USE_TLS

    @property
    def is_configured(self) -> bool:
        """Check if SMTP and destination email are fully configured."""
        has_dest = bool(settings.RECRUITER_NOTIFICATION_EMAIL and settings.RECRUITER_NOTIFICATION_EMAIL.strip())
        has_auth = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)
        return has_dest and has_auth

    def _get_password(self) -> Optional[str]:
        """Extract secret password value safely."""
        if settings.SMTP_PASSWORD:
            return settings.SMTP_PASSWORD.get_secret_value()
        return None

    def _build_email_message(
        self,
        recipient_email: str,
        full_name: str,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        channel: str = "whatsapp",
        answers: Optional[Dict[str, Any]] = None,
        cv_info: Optional[Dict[str, Any]] = None,
        match_score: float = 0.0,
        target_domains: Optional[List[str]] = None,
    ) -> MIMEMultipart:
        """Construct multi-part MIME email (Plaintext + HTML)."""
        app_name = settings.APP_NAME or "AI Recruitment Bot"
        company_name = settings.COMPANY_NAME or "Recrutement"
        sender_email = settings.SMTP_FROM or settings.SMTP_USER or f"noreply@{settings.SMTP_HOST}"

        subject = f"[{app_name}] Nouvelle Candidature : {full_name} ({channel.upper()})"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Date"] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

        phone_display = phone_number or "Non renseigné"
        email_display = email or "Non renseigné"
        date_str = datetime.utcnow().strftime("%d/%m/%Y à %H:%M UTC")

        # Prepare Q&A text and HTML
        answers_text_lines = []
        answers_html_cards = []

        if answers:
            for q_key, ans in answers.items():
                clean_ans = str(ans).strip()
                answers_text_lines.append(f"- {q_key}: {clean_ans}")
                answers_html_cards.append(
                    f"""
                    <div style="background-color: #f8fafc; border-left: 4px solid #2563eb; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px;">
                        <strong style="color: #1e293b; font-size: 14px; display: block; margin-bottom: 4px;">{html.escape(str(q_key))}</strong>
                        <div style="color: #334155; font-size: 14px; white-space: pre-wrap;">{html.escape(clean_ans)}</div>
                    </div>
                    """
                )
        else:
            answers_text_lines.append("Aucune réponse enregistrée.")
            answers_html_cards.append("<p style='color: #64748b;'>Aucune réponse enregistrée.</p>")

        answers_text_block = "\n".join(answers_text_lines)
        answers_html_block = "\n".join(answers_html_cards)

        # CV Info
        cv_text = ""
        cv_html = ""
        if cv_info:
            filename = cv_info.get("filename") or "CV non spécifié"
            summary = cv_info.get("summary") or "Aucun résumé disponible."
            cv_text = f"\n--- CV DU CANDIDAT ---\nFichier : {filename}\nScore matching : {match_score}%\nDomaines : {', '.join(target_domains or [])}\nRésumé : {summary}\n"
            cv_html = f"""
            <div style="background-color: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin-top: 16px;">
                <h4 style="margin-top: 0; color: #065f46; font-size: 15px;">📄 CV Analysé : {html.escape(filename)}</h4>
                <p style="margin: 4px 0; color: #047857;"><strong>Score de compatibilité :</strong> {match_score:.1f}%</p>
                <p style="margin: 4px 0; color: #047857;"><strong>Domaines ciblés :</strong> {html.escape(', '.join(target_domains or ['Non spécifié']))}</p>
                <p style="margin: 8px 0 0 0; color: #064e3b; font-size: 13px;"><em>{html.escape(summary)}</em></p>
            </div>
            """

        # 1. Plaintext Body
        text_body = f"""NOUVELLE CANDIDATURE REÇUE
===========================
Entreprise : {company_name}
Candidat   : {full_name}
Téléphone  : {phone_display}
Email      : {email_display}
Canal      : {channel.upper()}
Date       : {date_str}
{cv_text}
--- RÉPONSES AU QUESTIONNAIRE DE PRÉSÉLECTION ---
{answers_text_block}

---
Notification automatique générée par {app_name}.
"""

        # 2. HTML Body
        html_body = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{html.escape(subject)}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #1e293b; background-color: #f1f5f9; margin: 0; padding: 24px;">
    <div style="max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); padding: 24px 32px; color: #ffffff;">
            <h2 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.025em;">{html.escape(company_name)} — Recrutement</h2>
            <p style="margin: 6px 0 0 0; font-size: 14px; opacity: 0.9;">Nouvelle candidature finalisée via {html.escape(channel.upper())}</p>
        </div>

        <!-- Content -->
        <div style="padding: 28px 32px;">
            
            <!-- Candidate Summary Card -->
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 24px;">
                <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 16px; color: #0f172a;">👤 Profil du Candidat</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tr>
                        <td style="padding: 4px 0; color: #64748b; width: 140px;"><strong>Nom complet :</strong></td>
                        <td style="padding: 4px 0; color: #0f172a; font-weight: 600;">{html.escape(full_name)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #64748b;"><strong>Téléphone :</strong></td>
                        <td style="padding: 4px 0; color: #0f172a;">{html.escape(phone_display)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #64748b;"><strong>Email :</strong></td>
                        <td style="padding: 4px 0; color: #0f172a;">{html.escape(email_display)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #64748b;"><strong>Canal :</strong></td>
                        <td style="padding: 4px 0; color: #0f172a;">{html.escape(channel.upper())}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0; color: #64748b;"><strong>Date de réception :</strong></td>
                        <td style="padding: 4px 0; color: #0f172a;">{html.escape(date_str)}</td>
                    </tr>
                </table>
                {cv_html}
            </div>

            <!-- Answers -->
            <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 16px; color: #0f172a;">💬 Réponses au Questionnaire de Présélection</h3>
            {answers_html_block}

        </div>

        <!-- Footer -->
        <div style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 16px 32px; font-size: 12px; color: #64748b; text-align: center;">
            Message automatique généré par <strong>{html.escape(app_name)}</strong> pour <strong>{html.escape(company_name)}</strong>.<br>
            Pour toute modification du système de notification, veuillez consulter les paramètres d'environnement.
        </div>

    </div>
</body>
</html>
"""

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        return msg

    def _send_sync(self, msg: MIMEMultipart, recipient_email: str) -> bool:
        """Synchronous SMTP worker run in thread pool."""
        password = self._get_password()
        if not password or not self.user:
            logger.warning("smtp_missing_credentials", user=bool(self.user), pwd=bool(password))
            return False

        try:
            if self.port == 465:
                # SSL direct
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as server:
                    server.login(self.user, password)
                    server.sendmail(msg["From"], [recipient_email], msg.as_string())
            else:
                # STARTTLS (typically 587 or 25)
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    if self.use_tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                    server.login(self.user, password)
                    server.sendmail(msg["From"], [recipient_email], msg.as_string())

            logger.info(
                "recruitment_email_sent_successfully",
                recipient=recipient_email,
                host=self.host,
                port=self.port,
            )
            return True

        except smtplib.SMTPAuthenticationError as auth_err:
            logger.error("smtp_auth_error", error=str(auth_err), user=self.user)
            return False
        except Exception as exc:
            logger.error("smtp_send_error", error=str(exc), host=self.host, port=self.port)
            return False

    async def send_recruitment_notification(
        self,
        full_name: str,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        channel: str = "whatsapp",
        answers: Optional[Dict[str, Any]] = None,
        cv_info: Optional[Dict[str, Any]] = None,
        match_score: float = 0.0,
        target_domains: Optional[List[str]] = None,
    ) -> bool:
        """
        Send an asynchronous email notification to the recruiter.
        If SMTP is not configured, logs an informational notice and returns False gracefully.
        """
        recipient_email = settings.RECRUITER_NOTIFICATION_EMAIL
        if not recipient_email or not recipient_email.strip():
            logger.info("recruitment_email_skipped_no_recipient_configured")
            return False

        if not self.user or not settings.SMTP_PASSWORD:
            logger.info(
                "recruitment_email_skipped_smtp_not_configured",
                recipient=recipient_email,
                has_user=bool(self.user),
                has_pwd=bool(settings.SMTP_PASSWORD),
            )
            return False

        try:
            msg = self._build_email_message(
                recipient_email=recipient_email.strip(),
                full_name=full_name,
                phone_number=phone_number,
                email=email,
                channel=channel,
                answers=answers,
                cv_info=cv_info,
                match_score=match_score,
                target_domains=target_domains,
            )
            return await asyncio.to_thread(self._send_sync, msg, recipient_email.strip())
        except Exception as exc:
            logger.error("recruitment_notification_unhandled_exception", error=str(exc))
            return False


email_service = EmailNotificationService()
