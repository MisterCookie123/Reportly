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
The data may arrive as plain text OR as a CSV with headers.
If it is a CSV, the columns are:
Content, Type, Posted, Impressions, Reach, Likes, Comments, Shares, Saves, 
Engagement Rate, Link Clicks, Video Views

Map them as follows:
- post_title: Content column (truncate to 80 chars if needed)
- post_type: Type column (Video/Image/Reel/Carousel)
- date: Posted column
- likes: Likes column (integer, default 0)
- comments: Comments column (integer, default 0)
- shares: Shares column (integer, default 0)
- saves: Saves column (integer, default 0)
- reach: Reach column (integer, default 0)
- impressions: Impressions column (integer, default 0)
- profile_visits: default 0 unless specified
- url_clicks: Link Clicks column (integer, default 0)
- video_views: Video Views column (integer, default 0)

Strip any % signs from Engagement Rate before using it.
Strip any quotes from Content before using it as post_title.
If the data is plain text instead of CSV, extract metrics as best you can.

STEP 2 — CALCULATE SCORES
For each post calculate EXACTLY using this formula:
impact_score = (saves x 10) + (shares x 5) + (profile_visits x 3) + (comments x 2) + (likes x 1) + (video_views / 100)
Round the final score to nearest integer.
Video views are divided by 100 to normalize them against other metrics.
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
  "video_views": number,
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

    BG          = (10/255, 10/255, 10/255)
    CARD_BG     = (17/255, 17/255, 17/255)
    CARD_BORDER = (30/255, 30/255, 30/255)
    WHITE       = (1, 1, 1)
    MUTED       = (110/255, 110/255, 110/255)
    ACCENT      = (0/255, 255/255, 255/255)
    GREEN       = (74/255, 222/255, 128/255)
    AMBER       = (251/255, 146/255, 60/255)
    RED         = (248/255, 113/255, 113/255)

    LEFT  = 2*cm
    RIGHT = page_width - 2*cm
    W     = RIGHT - LEFT

    def sc(rgb): c.setFillColorRGB(*rgb)
    def ss(rgb): c.setStrokeColorRGB(*rgb)

    def bg():
        sc(BG)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    def hline(y, color=CARD_BORDER, width=0.5):
        ss(color)
        c.setLineWidth(width)
        c.line(LEFT, y, RIGHT, y)

    def card(x, y, w, h, border=CARD_BORDER, radius=6):
        sc(CARD_BG)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        ss(border)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)

    def label(text, x, y, color=MUTED):
        sc(color)
        c.setFont("Helvetica", 7)
        c.drawString(x, y, text.upper())

    def body(text, x, y, size=9, color=WHITE, max_w=None, font="Helvetica"):
        if max_w is None:
            max_w = W
        sc(color)
        c.setFont(font, size)
        lines = simpleSplit(str(text), font, size, max_w)
        for line in lines:
            c.drawString(x, y, line)
            y -= size * 1.6
        return y

    def heading(text, x, y, size=10, color=WHITE):
        sc(color)
        c.setFont("Helvetica-Bold", size)
        c.drawString(x, y, text)
        return y - size * 1.8

    def section(text, y):
        hline(y + 8, color=CARD_BORDER)
        sc(MUTED)
        c.setFont("Helvetica", 7)
        c.drawString(LEFT, y, text.upper())
        return y - 20

    def chk(y, needed=2.5*cm):
        if y < needed:
            c.showPage()
            bg()
            return page_height - 2*cm
        return y

    bg()

    cur = page_height - 1.6*cm
    sc(WHITE)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(LEFT, cur, "Performance Report")
    sc(MUTED)
    c.setFont("Helvetica", 8)
    c.drawRightString(RIGHT, cur, datetime.now().strftime("%B %Y"))
    cur -= 0.35*cm
    hline(cur)
    cur -= 0.9*cm

    score  = last_report.get("brand_health_score", 0)
    health = last_report.get("business_health", "N/A")
    sc_color = GREEN if health == "Good" else (AMBER if health == "Needs Attention" else RED)

    card_h = 3*cm
    card_y = cur - card_h
    card(LEFT, card_y, W, card_h, border=CARD_BORDER, radius=8)

    sc(ACCENT)
    c.setFont("Helvetica-Bold", 48)
    c.drawCentredString(page_width/2, card_y + card_h - 1.5*cm, str(score))

    sc(MUTED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(page_width/2, card_y + 0.85*cm, "BRAND HEALTH SCORE")

    sc(sc_color)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(page_width/2, card_y + 0.38*cm, health.upper())

    cur = card_y - 0.9*cm

    trend    = last_report.get("trend_analysis", "")
    followup = last_report.get("battle_plan_followup", "")
    if trend and trend != "First report — no trend data yet.":
        cur = chk(cur)
        cur = section("Month over Month", cur)
        cur = body(trend, LEFT, cur, size=9, color=MUTED, max_w=W)
        cur -= 4
        if followup and followup != "N/A":
            cur = body(f"Previous cycle: {followup}", LEFT, cur,
                       size=8, color=MUTED, max_w=W)
        cur -= 12

    cur = chk(cur)
    cur = section("Overview", cur)
    executive = last_report.get("executive_summary", "")
    if executive:
        cur = body(executive, LEFT, cur, size=9, color=MUTED, max_w=W)
    cur -= 12

    cf = last_report.get("save_to_reach_client_friendly", "")
    if cf:
        cur = chk(cur, 2*cm)
        lines = simpleSplit(cf, "Helvetica", 9, W - 20)
        needed_h = max(1.2*cm, len(lines) * 9 * 1.6 + 0.7*cm)
        cy = cur - needed_h
        card(LEFT, cy, W, needed_h, border=CARD_BORDER)
        label("Audience Signal", LEFT + 8, cy + needed_h - 0.38*cm)
        text_y = cy + needed_h - 0.7*cm
        sc(WHITE)
        c.setFont("Helvetica", 9)
        for line in lines:
            c.drawString(LEFT + 8, text_y, line)
            text_y -= 9 * 1.6
        cur = cy - 0.6*cm

    cur = chk(cur)
    cur = section("Top Performers", cur)

    posts     = last_report.get("posts", [])
    top_posts = sorted(posts, key=lambda x: x.get("impact_score", 0), reverse=True)[:3]
    max_sc    = max((p.get("impact_score", 1) for p in top_posts), default=1) or 1

    for i, post in enumerate(top_posts):
        cur = chk(cur, 2*cm)
        row_h = 1.6*cm
        row_y = cur - row_h
        card(LEFT, row_y, W, row_h, border=CARD_BORDER)

        sc(MUTED)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(LEFT + 10, row_y + row_h - 0.5*cm, f"0{i+1}")

        title_lines = simpleSplit(
            post.get("post_title", ""), "Helvetica-Bold", 9, W - 90
        )
        sc(WHITE)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(LEFT + 28, row_y + row_h - 0.5*cm,
                     title_lines[0] if title_lines else "")

        sv = post.get("impact_score", 0)
        sc(ACCENT)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(RIGHT - 8, row_y + row_h - 0.5*cm, str(sv))

        rating = post.get("efficiency_rating", "")
        rc = GREEN if rating == "High-Value Content" else (
            RED if rating == "Low-Efficiency Growth" else AMBER)
        sc(rc)
        c.setFont("Helvetica", 7)
        c.drawString(LEFT + 28, row_y + 0.45*cm, rating)

        bar_w = W - 90
        sc((30/255, 30/255, 30/255))
        c.roundRect(LEFT + 28, row_y + 0.2*cm, bar_w, 0.15*cm, 2, fill=1, stroke=0)
        filled = max(bar_w * min(sv/max_sc, 1), 0)
        if filled > 0:
            sc(ACCENT)
            c.roundRect(LEFT + 28, row_y + 0.2*cm, filled, 0.15*cm, 2, fill=1, stroke=0)

        cur = row_y - 0.3*cm

    cur -= 8
    cur = chk(cur)
    cur = section("Key Takeaways", cur)

    for ins in last_report.get("key_insights", []):
        cur = chk(cur, 1.5*cm)
        lines = simpleSplit(f"— {ins}", "Helvetica", 9, W)
        for line in lines:
            sc(MUTED)
            c.setFont("Helvetica", 9)
            c.drawString(LEFT, cur, line)
            cur -= 9 * 1.6
        cur -= 4

    cur -= 8
    cur = chk(cur)
    cur = section("Strategic Direction", cur)
    nv = last_report.get("next_month_vision", "")
    if nv:
        cur = body(nv, LEFT, cur, size=9, color=MUTED, max_w=W)

    c.save()
    buffer.seek(0)
    cn, mo, yr = get_file_metadata(last_report)
    return send_file(buffer, as_attachment=True,
                     download_name=f"{cn}_Performance_Report_{mo}_{yr}.pdf",
                     mimetype="application/pdf")

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

    BG          = (10/255, 10/255, 10/255)
    CARD_BG     = (17/255, 17/255, 17/255)
    CARD_BORDER = (30/255, 30/255, 30/255)
    WHITE       = (1, 1, 1)
    MUTED       = (110/255, 110/255, 110/255)
    ACCENT      = (0/255, 255/255, 255/255)
    GREEN       = (74/255, 222/255, 128/255)
    AMBER       = (251/255, 146/255, 60/255)
    RED         = (248/255, 113/255, 113/255)
    BLUE        = (59/255, 130/255, 246/255)

    LEFT  = 2*cm
    RIGHT = page_width - 2*cm
    W     = RIGHT - LEFT

    def sc(rgb): c.setFillColorRGB(*rgb)
    def ss(rgb): c.setStrokeColorRGB(*rgb)

    def bg():
        sc(BG)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    def hline(y, color=CARD_BORDER, width=0.5):
        ss(color)
        c.setLineWidth(width)
        c.line(LEFT, y, RIGHT, y)

    def card(x, y, w, h, border=CARD_BORDER, radius=6):
        sc(CARD_BG)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        ss(border)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)

    def body(text, x, y, size=9, color=WHITE, max_w=None, font="Helvetica"):
        if max_w is None:
            max_w = W
        sc(color)
        c.setFont(font, size)
        lines = simpleSplit(str(text), font, size, max_w)
        for line in lines:
            c.drawString(x, y, line)
            y -= size * 1.6
        return y

    def section(text, y):
        hline(y + 8, color=CARD_BORDER)
        sc(MUTED)
        c.setFont("Helvetica", 7)
        c.drawString(LEFT, y, text.upper())
        return y - 20

    def chk(y, needed=2.5*cm):
        if y < needed:
            c.showPage()
            bg()
            draw_header()
            return page_height - 2*cm
        return y

    def draw_header():
        cur = page_height - 1.6*cm
        sc(WHITE)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(LEFT, cur, "Strategic Analysis")
        sc(MUTED)
        c.setFont("Helvetica", 8)
        c.drawRightString(RIGHT, cur, datetime.now().strftime("%B %Y"))
        hline(cur - 0.35*cm)

    bg()
    draw_header()
    cur = page_height - 2.5*cm

    trend    = last_report.get("trend_analysis", "")
    followup = last_report.get("battle_plan_followup", "")
    if trend and trend != "First report — no trend data yet.":
        cur = section("Trend Analysis", cur)
        cur = body(trend, LEFT, cur, size=9, color=MUTED, max_w=W)
        cur -= 4
        if followup and followup != "N/A":
            cur = body(f"Previous cycle: {followup}", LEFT, cur,
                       size=8, color=MUTED, max_w=W)
        cur -= 16

    cur = chk(cur)
    cur = section("Content Review", cur)

    for item in last_report.get("kill_list", []):
        cur = chk(cur, 2.8*cm)

        reason      = item.get("reason", "")
        replacement = item.get("replacement", "")
        title       = item.get("post_title", "")

        reason_lines      = simpleSplit(f"Analysis: {reason}", "Helvetica", 8, W - 20)
        replacement_lines = simpleSplit(f"Recommendation: {replacement}", "Helvetica", 8, W - 20)
        title_lines       = simpleSplit(title, "Helvetica-Bold", 9, W - 20)

        needed_h = (
            0.5*cm +
            len(title_lines) * 9 * 1.6 +
            len(reason_lines) * 8 * 1.6 +
            len(replacement_lines) * 8 * 1.6 +
            0.3*cm
        )

        cy = cur - needed_h
        card(LEFT, cy, W, needed_h, border=CARD_BORDER)

        text_y = cy + needed_h - 0.5*cm

        sc(WHITE)
        c.setFont("Helvetica-Bold", 9)
        for line in title_lines:
            c.drawString(LEFT + 10, text_y, line)
            text_y -= 9 * 1.6

        text_y -= 4
        sc(MUTED)
        c.setFont("Helvetica", 8)
        for line in reason_lines:
            c.drawString(LEFT + 10, text_y, line)
            text_y -= 8 * 1.6

        text_y -= 4
        sc(BLUE)
        c.setFont("Helvetica", 8)
        for line in replacement_lines:
            c.drawString(LEFT + 10, text_y, line)
            text_y -= 8 * 1.6

        cur = cy - 0.4*cm

    cur -= 8
    cur = chk(cur)
    cur = section("Format Performance", cur)

    fv = last_report.get("format_velocity", "")
    if fv:
        cur = body(fv, LEFT, cur, size=9, color=MUTED, max_w=W)
    cur -= 12

    cur = chk(cur)
    cur = section("Engagement Depth", cur)

    cf      = last_report.get("save_to_reach_client_friendly", "")
    ratio   = last_report.get("save_to_reach_ratio", "N/A")
    cf_lines    = simpleSplit(cf, "Helvetica", 8, W - 100) if cf else []
    needed_h = max(1.2*cm, len(cf_lines) * 8 * 1.6 + 0.7*cm)

    ratio_y = cur - needed_h
    card(LEFT, ratio_y, W, needed_h, border=CARD_BORDER)

    sc(ACCENT)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(LEFT + 10, ratio_y + needed_h - 0.45*cm, ratio)

    text_y = ratio_y + needed_h - 0.75*cm
    sc(MUTED)
    c.setFont("Helvetica", 8)
    for line in cf_lines:
        c.drawString(LEFT + 10, text_y, line)
        text_y -= 8 * 1.6

    cur = ratio_y - 0.7*cm

    cur = chk(cur)
    cur = section("Post Performance Index", cur)

    sorted_posts = sorted(
        last_report.get("posts", []),
        key=lambda x: x.get("impact_score", 0),
        reverse=True
    )
    max_sv = max((p.get("impact_score", 1) for p in sorted_posts), default=1) or 1

    hh = 0.5*cm
    hy = cur - hh
    card(LEFT, hy, W, hh, border=CARD_BORDER, radius=4)
    sc(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(LEFT + 8, hy + 0.17*cm, "POST")
    c.drawString(RIGHT - 5.5*cm, hy + 0.17*cm, "SCORE")
    c.drawString(RIGHT - 3.5*cm, hy + 0.17*cm, "RATING")
    cur = hy - 0.15*cm

    for i, post in enumerate(sorted_posts):
        cur = chk(cur, 1.2*cm)
        rh  = 0.7*cm
        ry  = cur - rh
        rbg = CARD_BG if i % 2 == 0 else (14/255, 14/255, 14/255)
        sc(rbg)
        c.roundRect(LEFT, ry, W, rh, 3, fill=1, stroke=0)
        ss(CARD_BORDER)
        c.setLineWidth(0.5)
        c.roundRect(LEFT, ry, W, rh, 3, fill=0, stroke=1)

        title_l = simpleSplit(
            post.get("post_title", ""), "Helvetica", 8, W - 5.8*cm - 16
        )
        sc(WHITE)
        c.setFont("Helvetica", 8)
        c.drawString(LEFT + 8, ry + 0.25*cm,
                     title_l[0] if title_l else "")

        sv_ = post.get("impact_score", 0)
        sc((30/255, 30/255, 30/255))
        c.roundRect(RIGHT - 5.5*cm, ry + 0.22*cm, 1.2*cm, 0.18*cm,
                    2, fill=1, stroke=0)
        filled = max(1.2*cm * min(sv_/max_sv, 1), 0)
        if filled > 0:
            sc(ACCENT)
            c.roundRect(RIGHT - 5.5*cm, ry + 0.22*cm, filled, 0.18*cm,
                        2, fill=1, stroke=0)
        sc(WHITE)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(RIGHT - 5.5*cm + 1.3*cm, ry + 0.25*cm, str(sv_))

        rating = post.get("efficiency_rating", "")
        rc = GREEN if rating == "High-Value Content" else (
            RED if rating == "Low-Efficiency Growth" else AMBER)
        sc(rc)
        c.setFont("Helvetica", 7)
        c.drawString(RIGHT - 3.5*cm, ry + 0.25*cm, rating[:20])
        cur = ry - 0.12*cm

    cur -= 12
    cur = chk(cur)
    cur = section("Strategic Recommendations", cur)

    for i, action in enumerate(last_report.get("battle_plan", [])):
        cur = chk(cur, 1.8*cm)

        action_lines = simpleSplit(action, "Helvetica", 9, W - 45)
        needed_h     = max(1.1*cm, len(action_lines) * 9 * 1.6 + 0.4*cm)
        wcy          = cur - needed_h
        card(LEFT, wcy, W, needed_h, border=CARD_BORDER)

        sc(MUTED)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(LEFT + 10, wcy + needed_h - 0.42*cm, f"0{i+1}")

        ay = wcy + needed_h - 0.42*cm
        sc(WHITE)
        c.setFont("Helvetica", 9)
        for line in action_lines:
            c.drawString(LEFT + 30, ay, line)
            ay -= 9 * 1.6

        cur = wcy - 0.25*cm

    cur -= 8
    cur = chk(cur)
    cur = section("Overall Recommendations", cur)

    for rec in last_report.get("overall_recommendations", []):
        cur = chk(cur, 1.2*cm)
        lines = simpleSplit(f"— {rec}", "Helvetica", 9, W)
        for line in lines:
            sc(MUTED)
            c.setFont("Helvetica", 9)
            c.drawString(LEFT, cur, line)
            cur -= 9 * 1.6
        cur -= 6

    c.save()
    buffer.seek(0)
    cn, mo, yr = get_file_metadata(last_report)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{cn}_Strategic_Analysis_{mo}_{yr}.pdf",
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