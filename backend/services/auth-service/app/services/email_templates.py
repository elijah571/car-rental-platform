from html import escape


def render_code_email(*, purpose: str, code: str) -> tuple[str, str]:
    if purpose == "verification":
        heading = "Verify your email address"
        description = "Enter this code to finish setting up your Drivewell account."
        action = "If you did not create a Drivewell account, you can safely ignore this email."
    elif purpose == "password reset":
        heading = "Reset your password"
        description = "Enter this code to choose a new password for your Drivewell account."
        action = "If you did not request a password reset, you can safely ignore this email."
    else:
        raise ValueError(f"Unsupported email purpose: {purpose}")

    text = (
        f"{heading}\n\n{description}\n\n"
        f"Your code: {code}\n\n"
        f"This code expires in 15 minutes. {action}\n\n"
        "Drivewell"
    )
    safe_code = escape(code)
    html = f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{escape(heading)}</title>
  </head>
  <body style="margin:0;background:#f3f5f8;color:#172033;font-family:Arial,Helvetica,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(description)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f5f8;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e4e8ef;border-radius:12px;">
          <tr><td style="padding:28px 32px 16px;border-bottom:1px solid #edf0f4;">
            <div style="font-size:22px;font-weight:700;letter-spacing:-0.4px;color:#173b67;">Drivewell</div>
          </td></tr>
          <tr><td style="padding:32px;">
            <h1 style="margin:0 0 12px;font-size:24px;line-height:1.3;color:#172033;">{escape(heading)}</h1>
            <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#536176;">{escape(description)}</p>
            <div style="padding:18px 20px;background:#f3f7fc;border:1px solid #dce7f4;border-radius:8px;text-align:center;">
              <div style="margin-bottom:8px;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#536176;">Your secure code</div>
              <div style="font-size:32px;font-weight:700;letter-spacing:8px;color:#173b67;">{safe_code}</div>
            </div>
            <p style="margin:20px 0 0;font-size:14px;line-height:1.6;color:#536176;">
              This code expires in 15 minutes. {escape(action)}
            </p>
          </td></tr>
          <tr><td style="padding:18px 32px;border-top:1px solid #edf0f4;font-size:12px;line-height:1.5;color:#7b8798;">
            Drivewell &middot; Your journey, made simple.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""
    return text, html
