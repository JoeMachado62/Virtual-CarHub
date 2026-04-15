from __future__ import annotations

import logging
from urllib.parse import quote

from app.core.config import settings
from app.core.security import create_email_login_token
from app.models.entities import OveVehicleDetail, User, Vehicle

logger = logging.getLogger("vch.email")


def _send_email(*, to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not settings.has_sendgrid:
        logger.warning("sendgrid_not_configured subject=%s to=%s", subject, to_email)
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Content, Email, Mail, To

        sg = SendGridAPIClient(settings.sendgrid_api_key)
        mail = Mail(
            from_email=Email(settings.sendgrid_from_email, settings.sendgrid_from_name),
            to_emails=To(to_email),
            subject=subject,
        )
        mail.add_content(Content("text/plain", text_body))
        mail.add_content(Content("text/html", html_body))
        response = sg.send(mail)
        logger.info("email_sent subject=%s to=%s status=%s", subject, to_email, response.status_code)
    except Exception as exc:
        logger.warning("email_send_failed subject=%s to=%s error=%s", subject, to_email, exc)


def _extract_best_vehicle_image(detail: OveVehicleDetail | None, vehicle: Vehicle | None) -> str | None:
    for entry in (detail.images_json if detail else []) or []:
        if isinstance(entry, str) and entry.strip():
            return entry.strip()
        if isinstance(entry, dict):
            raw_url = entry.get("url")
            if isinstance(raw_url, str) and raw_url.strip():
                return raw_url.strip()

    for raw_url in (vehicle.images if vehicle else []) or []:
        if isinstance(raw_url, str) and raw_url.strip():
            return raw_url.strip()

    return None


def _vehicle_title(vehicle: Vehicle | None, vin: str) -> str:
    if not vehicle:
        return vin
    parts = [str(vehicle.year), vehicle.make, vehicle.model, vehicle.trim or ""]
    return " ".join(part for part in parts if part).strip() or vin


def _dashboard_magic_link(*, user: User, vin: str) -> str:
    token = create_email_login_token(user.id)
    base = settings.public_web_base_url.rstrip("/")
    return f"{base}/dashboard?vin={quote(vin)}&email_login_token={quote(token)}"


def send_condition_report_ready_email(
    *,
    user: User,
    vin: str,
    vehicle: Vehicle | None,
    detail: OveVehicleDetail | None,
    report_url: str | None,
) -> None:
    if not user.email:
        logger.warning("condition_report_email_skipped_missing_email user_id=%s vin=%s", user.id, vin)
        return

    vehicle_title = _vehicle_title(vehicle, vin)
    hero_image = _extract_best_vehicle_image(detail, vehicle)
    dashboard_url = _dashboard_magic_link(user=user, vin=vin)
    report_cta_url = report_url or dashboard_url
    greeting = f"Hi {user.first_name}" if user.first_name else "Hi"

    hero_block = (
        f"""
  <div style="margin:0 0 20px;">
    <img src="{hero_image}" alt="{vehicle_title}" style="width:100%;display:block;border-radius:18px;object-fit:cover;max-height:280px;" />
  </div>
"""
        if hero_image
        else ""
    )

    report_button_label = "View Original Auction Report" if report_url else "Open My Garage"
    html_body = f"""\
<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:28px;background:#f5f1e8;">
  <div style="background:linear-gradient(180deg,#fff9f0 0%,#ffffff 100%);border:1px solid #eadfce;border-radius:28px;padding:28px;box-shadow:0 14px 40px rgba(70,54,32,0.08);">
    <div style="display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:#d9efe2;color:#176543;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">
      Condition Report Ready
    </div>
    <h2 style="margin:16px 0 8px;color:#1f2937;font-size:30px;line-height:1.1;">Your report for {vehicle_title} is ready.</h2>
    <p style="margin:0 0 18px;color:#51606f;font-size:16px;line-height:1.6;">
      {greeting}, your auction condition report has finished processing. Use the button below to jump straight back into your Virtual CarHub back office.
    </p>
    {hero_block}
    <div style="display:grid;gap:10px;margin:0 0 18px;">
      <a href="{dashboard_url}" style="display:block;text-align:center;background:#1d4ed8;color:#ffffff;padding:14px 18px;border-radius:14px;text-decoration:none;font-weight:700;">
        Open My Garage
      </a>
      <a href="{report_cta_url}" style="display:block;text-align:center;background:#eef4ff;color:#1d4ed8;padding:14px 18px;border-radius:14px;text-decoration:none;font-weight:700;border:1px solid #c9dafd;">
        {report_button_label}
      </a>
    </div>
    <div style="display:grid;gap:8px;padding:16px 18px;border-radius:18px;background:#f8fafc;border:1px solid #e5e7eb;">
      <div style="font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:0.06em;font-weight:700;">Vehicle</div>
      <div style="font-size:18px;color:#111827;font-weight:700;">{vehicle_title}</div>
      <div style="font-size:14px;color:#6b7280;">VIN {vin}</div>
    </div>
    <p style="margin:18px 0 0;color:#6b7280;font-size:13px;line-height:1.6;">
      This sign-in link expires in {settings.email_login_expire_minutes} minutes for security.
    </p>
  </div>
</div>"""

    text_body = (
        f"{greeting},\n\n"
        f"Your condition report for {vehicle_title} is ready.\n\n"
        f"Open My Garage: {dashboard_url}\n"
        f"{report_button_label}: {report_cta_url}\n\n"
        f"VIN: {vin}\n\n"
        f"This sign-in link expires in {settings.email_login_expire_minutes} minutes.\n\n"
        "Virtual CarHub"
    )

    _send_email(
        to_email=user.email,
        subject=f"Your Condition Report Is Ready: {vehicle_title}",
        html_body=html_body,
        text_body=text_body,
    )
