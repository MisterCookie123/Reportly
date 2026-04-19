from flask import (
    Flask, render_template, request, jsonify,
    send_file, session, redirect, url_for
)
from openai import OpenAI
from dotenv import load_dotenv
from functools import wraps
import os
import json
import io
import uuid
from datetime import datetime

from auth import (
    init_db, create_user, authenticate_user,
    get_user_by_id, save_report_to_db, get_reports_from_db
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

init_db()

current_report_store = {}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith(
                ("/generate", "/download", "/fetch-instagram", "/history")
            ):
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    user_id = session.get("user_id")
    if user_id:
        return get_user_by_id(user_id)
    return None


def get_session_id():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def get_report(user_id: str) -> dict:
    return current_report_store.get(user_id, {})


def save_report(user_id: str, report: dict):
    save_report_to_db(user_id, report)
    current_report_store[user_id] = report


def get_history(user_id: str) -> list:
    return get_reports_from_db(user_id, limit=6)


def calculate_format_velocity(posts):
    if not posts:
        return "Not enough data to determine format velocity."

    type_scores = {}
    type_counts = {}
    for post in posts:
        ptype = post.get("post_type", "Unknown")
        score = post.get("impact_score", 0)
        type_scores[ptype] = type_scores.get(ptype, 0) + score
        type_counts[ptype] = type_counts.get(ptype, 0) + 1

    if not type_scores:
        return "Not enough data to determine format velocity."

    averages = {
        ptype: round(type_scores[ptype] / type_counts[ptype])
        for ptype in type_scores
    }
    best_type = max(averages, key=averages.get)
    best_avg  = averages[best_type]
    comparisons = [
        f"{pt}s avg {avg} pts ({type_counts[pt]} posts)"
        for pt, avg in sorted(averages.items(), key=lambda x: x[1], reverse=True)
    ]

    if len(averages) == 1:
        return (
            f"{best_type}s are the only format used this month — "
            f"avg impact score {best_avg}. Test a second format next month."
        )

    second_type = sorted(averages, key=averages.get, reverse=True)[1]
    second_avg  = averages[second_type]
    delta = best_avg - second_avg
    pct   = round((delta / second_avg) * 100) if second_avg > 0 else 0
    return (
        f"{best_type}s are outperforming {second_type}s by {pct}% "
        f"({best_avg} vs {second_avg} avg impact score). "
        f"Full breakdown: {' · '.join(comparisons)}."
    )


def build_structured_prompt(raw_posts):
    lines = ["STRUCTURED SOCIAL MEDIA DATA — ANALYZE THE FOLLOWING POSTS:\n"]
    for i, post in enumerate(raw_posts, 1):
        lines += [
            f"--- POST {i} ---",
            f"Title: {post.get('title', 'Untitled')}",
            f"Type: {post.get('type', 'Unknown')}",
            f"Date: {post.get('date', 'Unknown')}",
            f"Likes: {post.get('likes', 0)}",
            f"Comments: {post.get('comments', 0)}",
            f"Shares: {post.get('shares', 0)}",
            f"Saves: {post.get('saves', 0)}",
            f"Reach: {post.get('reach', 0)}",
            f"Profile Visits: {post.get('profile_visits', 0)}",
            f"URL Clicks: {post.get('url_clicks', 0)}",
            "",
        ]
    return "\n".join(lines)


def build_history_context(history):
    if not history:
        return ""
    lines = ["\n\n=== PREVIOUS REPORT HISTORY (for trend analysis) ===\n"]
    for i, old in enumerate(reversed(history), 1):
        lines += [
            f"--- Report {i} months ago ({old.get('_saved_at', 'unknown')[:10]}) ---",
            f"Brand Health Score: {old.get('brand_health_score', 'N/A')}",
            f"Business Health: {old.get('business_health', 'N/A')}",
            f"Top Post: {old.get('top_performing_post', 'N/A')}",
            f"Worst Post: {old.get('worst_performing_post', 'N/A')}",
        ]
        for step in old.get("battle_plan", []):
            lines.append(f"  - {step}")
        lines.append("")
    lines.append(
        "Use this history to identify trends and check if the previous "
        "battle plan appears to have been followed.\n"
    )
    return "\n".join(lines)


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/auth/signup", methods=["POST"])
def signup():
    data     = request.json or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    success, msg = create_user(email, password)
    if not success:
        return jsonify({"error": msg}), 400

    ok, user = authenticate_user(email, password)
    if ok:
        session["user_id"]    = user["id"]
        session["user_email"] = user["email"]
        session.permanent     = True

    return jsonify({"message": msg}), 201


@app.route("/auth/login", methods=["POST"])
def login():
    data     = request.json or {}
    email    = data.get("email", "").strip()
    password = data.get("password", "")

    ok, user = authenticate_user(email, password)
    if not ok:
        return jsonify({"error": "Incorrect email or password."}), 401

    session["user_id"]    = user["id"]
    session["user_email"] = user["email"]
    session.permanent     = True

    return jsonify({"message": "Logged in successfully."}), 200


@app.route("/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."}), 200


@app.route("/auth/me", methods=["GET"])
@login_required
def me():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({
        "id":         user["id"],
        "email":      user["email"],
        "created_at": user["created_at"],
    })


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
@login_required
def generate():
    user_id = session["user_id"]
    body    = request.json or {}

    raw_posts = body.get("posts")
    raw_text  = body.get("data", "")

    if raw_posts and isinstance(raw_posts, list) and len(raw_posts) > 0:
        user_data       = build_structured_prompt(raw_posts)
        format_velocity = calculate_format_velocity(raw_posts)
    elif raw_text:
        user_data       = raw_text
        format_velocity = None
    else:
        return jsonify({"error": "No data provided"}), 400

    history         = get_history(user_id)
    history_context = build_history_context(history)
    full_prompt     = user_data + history_context

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are a precise social media analyst. You extract numbers from messy data and calculate scores mechanically.

STEP 1 — EXTRACT METRICS
For every post mentioned in the data, extract these numbers:
- post_title: name or description of the post
- likes: number of likes (default 0 if missing)
- comments: number of comments (default 0 if missing)
- shares: number of shares (default 0 if missing)
- saves: number of saves (default 0 if missing)
- reach: total reach (default 0 if missing)
- profile_visits: profile visits from this post (default 0 if missing)
- url_clicks: URL clicks (default 0 if missing)

STEP 2 — CALCULATE SCORES
For each post calculate EXACTLY using this formula:
impact_score = (saves x 10) + (shares x 5) + (profile_visits x 3) + (comments x 2) + (likes x 1)
Do the math yourself. Do not guess or estimate.

STEP 3 — EFFICIENCY RATING
Calculate conversion_rate = (profile_visits / reach) x 100
If reach > 1000 AND conversion_rate < 1 AND saves < 20 → efficiency_rating = "Low-Efficiency Growth"
If saves > 0 AND (saves / reach) x 100 > 2 → efficiency_rating = "High-Value Content"
Otherwise → efficiency_rating = "Average"

STEP 4 — STRATEGIC ACTIONS PER POST
For each post assign exactly 3 actions based on these rules:
- If saves > 100 → "Create a 3-part series on this topic"
- If url_clicks = 0 AND (likes + shares + comments) > 100 → "Add a strong Call-to-Action (CTA) to drive link clicks"
- If impact_score > 1000 → "Boost this post with paid budget — it has proven organic traction"
- If impact_score < 100 AND reach > 500 → "Rethink content format — high reach but low engagement signals wrong content type"
- If shares > saves → "Optimize for saves not shares — saves indicate purchase intent"
- Default if no rules match → "Test a different content format for this topic"

STEP 5 — OVERALL ANALYSIS
- top_performing_post: post with highest impact_score
- worst_performing_post: post with lowest impact_score
- business_health: "Good" / "Needs Attention" / "Critical"
- overall_summary: 2-3 sentences in plain language for a business owner
- executive_summary: 3 sentences of CEO-speak explaining ROI and value delivered
- next_month_vision: one high level goal for next month
- key_insights: exactly 3 insights based on actual numbers
- overall_recommendations: exactly 3 recommendations based on patterns
- kill_list: the 2 worst performing posts with reason and replacement suggestion
- format_velocity: SET TO THE STRING "CALCULATED"
- save_to_reach_ratio: calculate as a percentage string
- save_to_reach_client_friendly: plain business language interpretation
- battle_plan: exactly 4 bullet points for the next 30 days
- brand_health_score: single number 0-100
- trend_analysis: if previous history provided, 2 sentences comparing this vs last month. Otherwise "First report — no trend data yet."
- battle_plan_followup: if previous battle plan exists, 1 sentence assessing if it was followed. Otherwise "N/A"

STEP 6 — OUTPUT
Return ONLY valid JSON. No markdown, no backticks, no extra text.

{
  "overall_summary": "string",
  "executive_summary": "string",
  "next_month_vision": "string",
  "business_health": "Good or Needs Attention or Critical",
  "brand_health_score": number,
  "posts": [
    {
      "post_title": "string",
      "post_type": "string",
      "impact_score": number,
      "efficiency_rating": "High-Value Content or Low-Efficiency Growth or Average",
      "top_3_strategic_actions": ["string", "string", "string"]
    }
  ],
  "top_performing_post": "string",
  "worst_performing_post": "string",
  "key_insights": ["string", "string", "string"],
  "overall_recommendations": ["string", "string", "string"],
  "kill_list": [
    { "post_title": "string", "reason": "string", "replacement": "string" }
  ],
  "format_velocity": "CALCULATED",
  "save_to_reach_ratio": "string",
  "save_to_reach_client_friendly": "string",
  "battle_plan": ["string", "string", "string", "string"],
  "trend_analysis": "string",
  "battle_plan_followup": "string"
}"""
            },
            {
                "role": "user",
                "content": f"Analyze this social media data and follow all steps precisely:\n\n{full_prompt}"
            }
        ]
    )

    raw = response.choices[0].message.content
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return jsonify({"report": {"raw_output": raw}})

    if format_velocity:
        report["format_velocity"] = format_velocity
    elif report.get("format_velocity") == "CALCULATED":
        report["format_velocity"] = calculate_format_velocity(
            report.get("posts", [])
        )

    save_report(user_id, report)
    return jsonify({"report": report})


def get_file_metadata(report):
    client_name = "Client"
    import re
    for text in [report.get("overall_summary", ""), report.get("executive_summary", "")]:
        for pattern in [
            r"for ([A-Z][a-zA-Z\s]+(?:Agency|Studio|Brand|Media|Marketing|Co|Inc|Ltd)?)",
            r"([A-Z][a-zA-Z\s]+(?:Agency|Studio|Brand|Media|Marketing))",
        ]:
            match = re.search(pattern, text)
            if match:
                found = match.group(1).strip()
                if 2 < len(found) < 40:
                    client_name = found.replace(" ", "_")
                    break
        if client_name != "Client":
            break
    now = datetime.now()
    return client_name, now.strftime("%B"), now.strftime("%Y")


@app.route("/download/client")
@login_required
def download_client():
    user_id     = session["user_id"]
    last_report = get_report(user_id)
    if not last_report:
        return "No report generated yet", 400

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import simpleSplit

    buffer = io.BytesIO()
    page_width, page_height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    BG          = (10/255,  10/255,  10/255)
    CARD_BG     = (17/255,  17/255,  17/255)
    CARD_BORDER = (34/255,  34/255,  34/255)
    CARD_LIGHT  = (40/255,  40/255,  40/255)
    WHITE       = (1, 1, 1)
    MUTED       = (136/255, 136/255, 136/255)
    CYAN        = (0/255,  255/255, 255/255)
    PURPLE      = (191/255,  0/255, 255/255)
    GREEN       = (74/255,  222/255, 128/255)
    AMBER       = (251/255, 146/255,  60/255)
    RED         = (248/255, 113/255, 113/255)

    def sc(rgb): c.setFillColorRGB(*rgb)
    def ss(rgb): c.setStrokeColorRGB(*rgb)

    def draw_bg():
        sc(BG)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    def draw_card(x, y, w, h, bg=CARD_BG, border=CARD_BORDER, radius=8):
        sc(bg)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        ss(border)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)

    def draw_line(y, color=PURPLE):
        ss(color)
        c.setLineWidth(0.5)
        c.line(2*cm, y, page_width - 2*cm, y)

    def draw_bar(x, y, w, h, pct, color=CYAN):
        sc(CARD_LIGHT)
        c.roundRect(x, y, w, h, 3, fill=1, stroke=0)
        filled = max(w * min(pct / 100, 1), 0)
        if filled > 0:
            sc(color)
            c.roundRect(x, y, filled, h, 3, fill=1, stroke=0)

    def txt(t, x, y, font="Helvetica", size=11, color=WHITE):
        sc(color)
        c.setFont(font, size)
        c.drawString(x, y, str(t))

    def ctxt(t, y, font="Helvetica", size=11, color=WHITE):
        sc(color)
        c.setFont(font, size)
        c.drawCentredString(page_width / 2, y, str(t))

    def mltxt(t, x, y, font="Helvetica", size=10, color=WHITE, max_w=None):
        if max_w is None:
            max_w = page_width - 4*cm
        sc(color)
        c.setFont(font, size)
        for line in simpleSplit(str(t), font, size, max_w):
            c.drawString(x, y, line)
            y -= size * 1.4
        return y

    def chk(y, thr=4*cm):
        if y < thr:
            c.showPage()
            draw_bg()
            return page_height - 2.5*cm
        return y

    draw_bg()
    draw_line(page_height - 1.5*cm, color=CARD_BORDER)

    score  = last_report.get("brand_health_score", 0)
    health = last_report.get("business_health", "N/A")
    cw, ch = 10*cm, 4.2*cm
    cx = page_width / 2 - cw / 2
    cy = page_height - 6.8*cm

    draw_card(cx, cy, cw, ch, bg=CARD_BG, border=CYAN, radius=10)
    ctxt(str(score), cy + ch - 1.3*cm, font="Helvetica-Bold", size=48, color=CYAN)
    ctxt("BRAND HEALTH SCORE", cy + 1.3*cm, font="Helvetica-Bold", size=8, color=MUTED)
    status_color = GREEN if health == "Good" else (AMBER if health == "Needs Attention" else RED)
    ctxt(f"STATUS: {health.upper()}", cy + 0.5*cm, font="Helvetica-Bold", size=9, color=status_color)

    cur = cy - 0.8*cm

    trend    = last_report.get("trend_analysis", "")
    followup = last_report.get("battle_plan_followup", "")
    if trend and trend != "First report — no trend data yet.":
        draw_line(cur, color=PURPLE)
        cur -= 0.7*cm
        txt("MONTH OVER MONTH", 2*cm, cur, font="Helvetica-Bold", size=12, color=CYAN)
        cur -= 0.5*cm
        cur = mltxt(trend, 2*cm, cur, size=10)
        if followup and followup != "N/A":
            cur -= 0.2*cm
            cur = mltxt(f"Battle Plan Follow-up: {followup}", 2*cm, cur, size=9, color=MUTED)
        cur -= 0.3*cm

    draw_line(cur, color=PURPLE)
    cur -= 0.7*cm
    txt("WHAT WE ACHIEVED THIS MONTH", 2*cm, cur, font="Helvetica-Bold", size=12, color=CYAN)
    cur -= 0.5*cm
    executive = last_report.get("executive_summary", "")
    if executive:
        cur = mltxt(executive, 2*cm, cur, size=10)
    cur -= 0.5*cm
    cur = chk(cur)

    cf = last_report.get("save_to_reach_client_friendly", "")
    if cf:
        ih  = 1.6*cm
        iy  = cur - ih
        draw_card(2*cm, iy, page_width - 4*cm, ih, bg=CARD_BG, border=CYAN, radius=8)
        txt("AUDIENCE INTEREST", 2.4*cm, iy + ih - 0.55*cm,
            font="Helvetica-Bold", size=8, color=MUTED)
        mltxt(cf, 2.4*cm, iy + 0.9*cm, font="Helvetica-Bold",
              size=10, color=GREEN, max_w=page_width - 5*cm)
        cur = iy - 0.6*cm

    cur = chk(cur)
    draw_line(cur, color=PURPLE)
    cur -= 0.7*cm

    posts     = last_report.get("posts", [])
    top_posts = sorted(posts, key=lambda x: x.get("impact_score", 0), reverse=True)[:3]
    max_sc    = max((p.get("impact_score", 1) for p in top_posts), default=1) or 1

    if top_posts:
        txt("TOP 3 WINS THIS MONTH", 2*cm, cur, font="Helvetica-Bold", size=12, color=CYAN)
        cur -= 0.5*cm
        for i, post in enumerate(top_posts):
            cur = chk(cur, 3.5*cm)
            wh  = 2.4*cm
            wy  = cur - wh
            draw_card(2*cm, wy, page_width - 4*cm, wh,
                      bg=CARD_BG, border=CARD_BORDER, radius=8)
            txt(f"0{i+1}", 2.4*cm, wy + wh - 0.65*cm,
                font="Helvetica-Bold", size=14, color=PURPLE)
            txt(post.get("post_title", "")[:52], 3.5*cm, wy + wh - 0.65*cm,
                font="Helvetica-Bold", size=10)
            rating = post.get("efficiency_rating", "")
            rc = GREEN if rating == "High-Value Content" else (
                RED if rating == "Low-Efficiency Growth" else AMBER)
            txt(rating.upper(), 3.5*cm, wy + 1.0*cm,
                font="Helvetica-Bold", size=8, color=rc)
            sv = post.get("impact_score", 0)
            draw_bar(3.5*cm, wy + 0.4*cm,
                     page_width - 4*cm - 1.5*cm - 2.5*cm,
                     0.22*cm, (sv / max_sc) * 100)
            txt(f"Score: {sv}", page_width - 4.2*cm, wy + wh - 0.65*cm,
                font="Helvetica-Bold", size=9, color=CYAN)
            cur = wy - 0.3*cm

    cur -= 0.3*cm
    cur = chk(cur)
    draw_line(cur, color=PURPLE)
    cur -= 0.7*cm

    insights = last_report.get("key_insights", [])
    if insights:
        txt("KEY TAKEAWAYS", 2*cm, cur, font="Helvetica-Bold", size=12, color=CYAN)
        cur -= 0.5*cm
        for ins in insights:
            cur = chk(cur, 2*cm)
            cur = mltxt(f"—  {ins}", 2.3*cm, cur, size=10,
                        max_w=page_width - 4.5*cm)
            cur -= 0.2*cm

    cur -= 0.3*cm
    cur = chk(cur)
    draw_line(cur, color=PURPLE)
    cur -= 0.7*cm

    nv = last_report.get("next_month_vision", "")
    if nv:
        txt("WHAT WE'RE BUILDING TOWARD NEXT MONTH", 2*cm, cur,
            font="Helvetica-Bold", size=12, color=CYAN)
        cur -= 0.5*cm
        mltxt(nv, 2*cm, cur, size=10)

    c.save()
    buffer.seek(0)
    cn, mo, yr = get_file_metadata(last_report)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{cn}_Performance_Report_{mo}_{yr}.pdf",
        mimetype="application/pdf"
    )


@app.route("/download/smm")
@login_required
def download_smm():
    user_id     = session["user_id"]
    last_report = get_report(user_id)
    if not last_report:
        return "No report generated yet", 400

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import simpleSplit

    buffer = io.BytesIO()
    page_width, page_height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    MIDNIGHT    = (18/255,  18/255,  18/255)
    CARD_BG     = (30/255,  30/255,  30/255)
    CARD_LIGHT  = (40/255,  40/255,  40/255)
    WHITE       = (1, 1, 1)
    MUTED       = (160/255, 160/255, 160/255)
    CYAN        = (0/255,  255/255, 255/255)
    PURPLE      = (191/255,  0/255, 255/255)
    GREEN       = (74/255,  222/255, 128/255)
    AMBER       = (251/255, 146/255,  60/255)
    RED         = (248/255, 113/255, 113/255)
    BLUE        = (59/255,  130/255, 246/255)

    def sc(rgb): c.setFillColorRGB(*rgb)
    def ss(rgb): c.setStrokeColorRGB(*rgb)

    def draw_bg():
        sc(MIDNIGHT)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    def draw_card(x, y, w, h, bg=CARD_BG, border=PURPLE, radius=8):
        sc(bg)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        ss(border)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)

    def draw_line(y, color=PURPLE):
        ss(color)
        c.setLineWidth(0.5)
        c.line(2*cm, y, page_width - 2*cm, y)

    def draw_bar(x, y, w, h, pct, color=CYAN):
        sc(CARD_LIGHT)
        c.roundRect(x, y, w, h, 3, fill=1, stroke=0)
        fw = max(w * min(pct / 100, 1), 0)
        if fw > 0:
            sc(color)
            c.roundRect(x, y, fw, h, 3, fill=1, stroke=0)

    def txt(t, x, y, font="Helvetica", size=11, color=WHITE):
        sc(color)
        c.setFont(font, size)
        c.drawString(x, y, str(t))

    def ctxt(t, y, font="Helvetica", size=11, color=WHITE):
        sc(color)
        c.setFont(font, size)
        c.drawCentredString(page_width / 2, y, str(t))

    def chk(y, thr=4*cm):
        if y < thr:
            c.showPage()
            draw_bg()
            draw_header()
            return page_height - 2.5*cm
        return y

    def draw_header():
        draw_line(page_height - 1.5*cm)

    draw_bg()
    draw_header()

    ctxt("SMM TACTICAL REPORT", page_height - 2.5*cm,
         font="Helvetica-Bold", size=20)
    ctxt("Internal Use Only — Do Not Share With Client",
         page_height - 3.1*cm, font="Helvetica", size=9, color=RED)

    cur = page_height - 3.8*cm
    draw_line(cur)
    cur -= 0.7*cm

    trend    = last_report.get("trend_analysis", "")
    followup = last_report.get("battle_plan_followup", "")
    if trend and trend != "First report — no trend data yet.":
        txt("TREND ANALYSIS", 2*cm, cur, font="Helvetica-Bold", size=13, color=CYAN)
        cur -= 0.5*cm
        for line in simpleSplit(trend, "Helvetica", 10, page_width - 4*cm):
            txt(line, 2*cm, cur, size=10)
            cur -= 0.45*cm
        if followup and followup != "N/A":
            cur -= 0.2*cm
            for line in simpleSplit(
                f"Battle Plan Check: {followup}", "Helvetica", 9, page_width - 4*cm
            ):
                txt(line, 2*cm, cur, size=9, color=MUTED)
                cur -= 0.4*cm
        cur -= 0.3*cm
        draw_line(cur)
        cur -= 0.7*cm

    txt("THE KILL LIST", 2*cm, cur, font="Helvetica-Bold", size=13, color=RED)
    txt("Posts to kill or completely rethink", 8*cm, cur,
        font="Helvetica", size=9, color=MUTED)
    cur -= 0.5*cm

    for item in last_report.get("kill_list", []):
        cur = chk(cur, 5*cm)
        ch_ = 2.8*cm
        cy_ = cur - ch_
        draw_card(2*cm, cy_, page_width - 4*cm, ch_, bg=CARD_BG, border=RED, radius=6)
        sc(RED)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(2.4*cm, cy_ + ch_ - 0.6*cm, "x")
        txt(item.get("post_title", "")[:55], 3.0*cm, cy_ + ch_ - 0.6*cm,
            font="Helvetica-Bold", size=10)
        ry = cy_ + ch_ - 1.1*cm
        for line in simpleSplit(
            f"Why: {item.get('reason', '')}", "Helvetica", 9, page_width - 5.5*cm
        ):
            txt(line, 2.4*cm, ry, size=9, color=MUTED)
            ry -= 0.35*cm
        ry2 = cy_ + 0.5*cm
        for line in simpleSplit(
            f"Replace with: {item.get('replacement', '')}", "Helvetica-Bold", 9,
            page_width - 5.5*cm
        ):
            txt(line, 2.4*cm, ry2, font="Helvetica-Bold", size=9, color=BLUE)
            ry2 -= 0.35*cm
        cur = cy_ - 0.4*cm

    cur -= 0.3*cm
    cur = chk(cur)
    draw_line(cur)
    cur -= 0.7*cm

    txt("FORMAT VELOCITY", 2*cm, cur, font="Helvetica-Bold", size=13, color=CYAN)
    cur -= 0.5*cm
    for line in simpleSplit(
        last_report.get("format_velocity", ""), "Helvetica", 10, page_width - 4*cm
    ):
        txt(line, 2*cm, cur, size=10)
        cur -= 0.45*cm

    cur -= 0.5*cm
    cur = chk(cur)
    draw_line(cur)
    cur -= 0.7*cm

    txt("SAVE-TO-REACH RATIO", 2*cm, cur, font="Helvetica-Bold", size=13, color=CYAN)
    cur -= 0.5*cm
    rh  = 1.8*cm
    ry_ = cur - rh
    draw_card(2*cm, ry_, page_width - 4*cm, rh, bg=CARD_BG, border=CYAN, radius=6)
    txt(f"Technical: {last_report.get('save_to_reach_ratio', 'N/A')}",
        2.4*cm, ry_ + rh - 0.6*cm, font="Helvetica-Bold", size=10, color=CYAN)
    txt(f"Meaning: {last_report.get('save_to_reach_client_friendly', '')}",
        2.4*cm, ry_ + 0.5*cm, size=9, color=MUTED)
    cur = ry_ - 0.7*cm
    cur = chk(cur)
    draw_line(cur)
    cur -= 0.7*cm

    txt("POST PERFORMANCE BREAKDOWN", 2*cm, cur,
        font="Helvetica-Bold", size=13, color=CYAN)
    cur -= 0.6*cm

    sorted_posts = sorted(
        last_report.get("posts", []),
        key=lambda x: x.get("impact_score", 0),
        reverse=True
    )
    max_sv = max((p.get("impact_score", 1) for p in sorted_posts), default=1) or 1

    hh = 0.55*cm
    hy = cur - hh
    draw_card(2*cm, hy, page_width - 4*cm, hh, bg=CARD_LIGHT, border=PURPLE, radius=4)
    txt("POST",   2.3*cm,           hy + 0.15*cm, font="Helvetica-Bold", size=8, color=PURPLE)
    txt("SCORE",  page_width-6.5*cm, hy + 0.15*cm, font="Helvetica-Bold", size=8, color=PURPLE)
    txt("RATING", page_width-4.8*cm, hy + 0.15*cm, font="Helvetica-Bold", size=8, color=PURPLE)
    cur = hy - 0.2*cm

    for i, post in enumerate(sorted_posts):
        cur = chk(cur, 3*cm)
        rh_ = 0.9*cm
        ry2 = cur - rh_
        rbg = CARD_BG if i % 2 == 0 else (25/255, 25/255, 25/255)
        draw_card(2*cm, ry2, page_width - 4*cm, rh_, bg=rbg, border=PURPLE, radius=4)
        txt(post.get("post_title", "")[:38], 2.3*cm, ry2 + 0.32*cm, size=8)
        sv_ = post.get("impact_score", 0)
        draw_bar(page_width-7.5*cm, ry2+0.3*cm, 2.5*cm, 0.25*cm, (sv_/max_sv)*100)
        txt(str(sv_), page_width-6.4*cm, ry2+0.32*cm,
            font="Helvetica-Bold", size=8, color=CYAN)
        rating = post.get("efficiency_rating", "")
        rc = GREEN if rating == "High-Value Content" else (
            RED if rating == "Low-Efficiency Growth" else AMBER)
        txt(rating[:18], page_width-4.8*cm, ry2+0.32*cm,
            font="Helvetica-Bold", size=7, color=rc)
        cur = ry2 - 0.15*cm

    cur -= 0.5*cm
    cur = chk(cur)
    draw_line(cur)
    cur -= 0.7*cm

    txt("4-WEEK BATTLE PLAN", 2*cm, cur, font="Helvetica-Bold", size=13, color=CYAN)
    cur -= 0.5*cm
    week_colors = [CYAN, PURPLE, GREEN, AMBER]

    for i, action in enumerate(last_report.get("battle_plan", [])):
        cur = chk(cur, 3*cm)
        wch = 1.4*cm
        wcy = cur - wch
        wc  = week_colors[i % 4]
        draw_card(2*cm, wcy, page_width - 4*cm, wch, bg=CARD_BG, border=wc, radius=6)
        txt(f"WEEK {i+1}", 2.4*cm, wcy + wch - 0.55*cm,
            font="Helvetica-Bold", size=8, color=wc)
        ay = wcy + wch - 0.55*cm
        for line in simpleSplit(action, "Helvetica", 9, page_width - 6.5*cm):
            txt(line, 4.2*cm, ay, size=9)
            ay -= 0.38*cm
        cur = wcy - 0.3*cm

    cur -= 0.3*cm
    cur = chk(cur)
    draw_line(cur)
    cur -= 0.7*cm

    txt("OVERALL RECOMMENDATIONS", 2*cm, cur,
        font="Helvetica-Bold", size=13, color=CYAN)
    cur -= 0.5*cm

    for rec in last_report.get("overall_recommendations", []):
        cur = chk(cur, 2*cm)
        for line in simpleSplit(
            f"->  {rec}", "Helvetica", 10, page_width - 4.5*cm
        ):
            txt(line, 2.3*cm, cur, size=10)
            cur -= 0.45*cm
        cur -= 0.2*cm

    c.save()
    buffer.seek(0)

    cn, mo, yr = get_file_metadata(last_report)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{cn}_SMM_Tactical_{mo}_{yr}.pdf",
        mimetype="application/pdf"
    )


@app.route("/fetch-instagram", methods=["POST"])
@login_required
def fetch_instagram():
    username = request.json.get("username", "").strip()
    if not username:
        return jsonify({"error": "No username provided"}), 400
    username = username.replace("@", "").replace(
        "https://www.instagram.com/", ""
    ).strip("/")
    try:
        posts_data = fetch_instagram_data(username)
        if not posts_data:
            return jsonify({"error": "No posts found or account is private"}), 404
        return jsonify({
            "success": True,
            "posts_count": len(posts_data),
            "formatted_data": format_for_reportly(posts_data),
            "raw_data": posts_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/history", methods=["GET"])
@login_required
def get_report_history():
    user_id = session["user_id"]
    history = get_history(user_id)
    summaries = [
        {
            "index":               i,
            "saved_at":            r.get("_saved_at", ""),
            "brand_health_score":  r.get("brand_health_score"),
            "business_health":     r.get("business_health"),
            "top_performing_post": r.get("top_performing_post"),
        }
        for i, r in enumerate(history)
    ]
    return jsonify({"history": summaries})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)