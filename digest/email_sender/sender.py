import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from digest.config import Config

logger = logging.getLogger(__name__)


def send_digest(html_content: str, plain_content: str, subject: str, config: Config) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_USER
    msg["To"] = config.RECIPIENT_EMAIL

    msg.attach(MIMEText(plain_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    logger.info(f"Sending digest to {config.RECIPIENT_EMAIL}...")

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
        smtp.sendmail(config.GMAIL_USER, config.RECIPIENT_EMAIL, msg.as_string())

    logger.info("Email sent successfully.")
