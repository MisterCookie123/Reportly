from flask import Flask, render_template, request, jsonify, send_file
from openai import OpenAI
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import os
import json
import io
from instagram import fetch_instagram_data, format_for_reportly

load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

last_report = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    global last_report
    data = request.json.get("data", "")

    if not data:
        return jsonify({"error": "No data provided"}), 400

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
- business_health: 
  If average impact_score > 500 → "Good"
  If average impact_score 200-500 → "Needs Attention"
  If average impact_score < 200 → "Critical"
- overall_summary: 2-3 sentences in plain language for a business owner
- executive_summary: 3 sentences of CEO-speak explaining ROI and value delivered
- next_month_vision: one high level goal for next month
- key_insights: exactly 3 insights based on actual numbers
- overall_recommendations: exactly 3 recommendations based on patterns
- kill_list: the 2 worst performing posts with specific reason why they failed 
  AND a specific replacement suggestion
  Example: "Kill the quote post — replace with a behind the scenes photo showing 
  your process"
- format_velocity: which content format is performing best right now and by how much
- save_to_reach_ratio: calculate the ratio as a percentage
- save_to_reach_interpretation: explain this metric in two ways:
  1. technical: "X% Save-to-Reach Ratio"
  2. client_friendly: translate into plain business language like 
  "High Customer Interest" or "Low Purchase Intent" with one sentence explanation
- battle_plan: exactly 4 bullet points of what to change in the next 30 days
- brand_health_score: a single number 0-100 representing overall brand health

STEP 6 — OUTPUT
Return ONLY a valid JSON object with no extra text, no markdown, no backticks.

{
  "overall_summary": "string",
  "executive_summary": "string",
  "next_month_vision": "string",
  "business_health": "Good or Needs Attention or Critical",
  "brand_health_score": number,
  "posts": [
    {
      "post_title": "string",
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
    {
      "post_title": "string",
      "reason": "string",
      "replacement": "string"
    }
  ],
  "save_to_reach_ratio": "string",
  "save_to_reach_client_friendly": "string",
  "battle_plan": ["string", "string", "string", "string"]
}"""
            },
            {
                "role": "user",
                "content": f"Analyze this social media data and follow all steps precisely:\n\n{data}"
            }
        ]
    )

    raw = response.choices[0].message.content

    try:
        report = json.loads(raw)
        last_report = report
    except json.JSONDecodeError:
        report = {"raw_output": raw}

    return jsonify({"report": report})


@app.route("/download/client")
def download_client():
    if not last_report:
        return "No report generated yet", 400

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    import io

    buffer = io.BytesIO()
    page_width, page_height = A4

    c = canvas.Canvas(buffer, pagesize=A4)

    MIDNIGHT = (18/255, 18/255, 18/255)
    CARD_BG = (30/255, 30/255, 30/255)
    CARD_LIGHT = (40/255, 40/255, 40/255)
    WHITE = (1, 1, 1)
    MUTED = (160/255, 160/255, 160/255)
    CYAN = (0/255, 255/255, 255/255)
    PURPLE = (191/255, 0/255, 255/255)
    GREEN = (74/255, 222/255, 128/255)
    AMBER = (251/255, 146/255, 60/255)
    RED = (248/255, 113/255, 113/255)

    def set_color(rgb):
        c.setFillColorRGB(*rgb)

    def set_stroke(rgb):
        c.setStrokeColorRGB(*rgb)

    def draw_background():
        set_color(MIDNIGHT)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    def draw_card(x, y, w, h, bg=CARD_BG, border=PURPLE, radius=8):
        set_color(bg)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        set_stroke(border)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)

    def draw_section_line(y):
        set_stroke(PURPLE)
        c.setLineWidth(0.5)
        c.line(2*cm, y, page_width - 2*cm, y)

    def draw_progress_bar(x, y, w, h, percent, color=CYAN, bg=CARD_LIGHT):
        set_color(bg)
        c.roundRect(x, y, w, h, 3, fill=1, stroke=0)
        filled_w = max(w * min(percent / 100, 1), 0)
        if filled_w > 0:
            set_color(color)
            c.roundRect(x, y, filled_w, h, 3, fill=1, stroke=0)

    def draw_text(text, x, y, font="Helvetica", size=11, color=WHITE):
        set_color(color)
        c.setFont(font, size)
        c.drawString(x, y, str(text))

    def draw_centered_text(text, y, font="Helvetica", size=11, color=WHITE):
        set_color(color)
        c.setFont(font, size)
        c.drawCentredString(page_width / 2, y, str(text))

    def new_page():
        draw_background()

    draw_background()

    c.setFont("Helvetica-Bold", 9)
    set_color(PURPLE)
    c.drawString(2*cm, page_height - 1.2*cm, "REPORTLY")
    set_color(MUTED)
    c.setFont("Helvetica", 9)
    c.drawRightString(page_width - 2*cm, page_height - 1.2*cm, "CONFIDENTIAL · CLIENT REPORT")

    draw_section_line(page_height - 1.5*cm)

    draw_centered_text(
        "MONTHLY PERFORMANCE REPORT",
        page_height - 2.5*cm,
        font="Helvetica-Bold",
        size=18,
        color=WHITE
    )
    draw_centered_text(
        "Prepared exclusively for you",
        page_height - 3.1*cm,
        font="Helvetica",
        size=10,
        color=MUTED
    )

    score = last_report.get('brand_health_score', 0)
    health = last_report.get('business_health', 'N/A')

    card_y = page_height - 7.5*cm
    card_h = 4*cm
    card_x = page_width / 2 - 5*cm
    card_w = 10*cm

    draw_card(card_x, card_y, card_w, card_h, bg=CARD_BG, border=CYAN, radius=10)

    draw_centered_text(
        str(score),
        card_y + card_h - 1.2*cm,
        font="Helvetica-Bold",
        size=42,
        color=CYAN
    )
    draw_centered_text(
        "BRAND HEALTH SCORE",
        card_y + 1.2*cm,
        font="Helvetica-Bold",
        size=8,
        color=MUTED
    )

    if health == "Good":
        status_color = GREEN
    elif health == "Needs Attention":
        status_color = AMBER
    else:
        status_color = RED

    draw_centered_text(
        f"STATUS: {health.upper()}",
        card_y + 0.5*cm,
        font="Helvetica-Bold",
        size=9,
        color=status_color
    )

    current_y = card_y - 0.8*cm
    draw_section_line(current_y)

    current_y -= 0.6*cm
    draw_text(
        "WHAT WE ACHIEVED THIS MONTH",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=11,
        color=CYAN
    )

    current_y -= 0.5*cm
    executive = last_report.get('executive_summary', '')
    if executive:
        from reportlab.lib.utils import simpleSplit
        words = simpleSplit(executive, "Helvetica", 10, page_width - 4*cm)
        for line in words:
            current_y -= 0.45*cm
            draw_text(line, 2*cm, current_y, font="Helvetica", size=10, color=WHITE)

    current_y -= 0.8*cm
    draw_section_line(current_y)
    current_y -= 0.6*cm

    client_friendly = last_report.get('save_to_reach_client_friendly', '')
    if client_friendly:
        draw_text(
            "AUDIENCE INTEREST",
            2*cm,
            current_y,
            font="Helvetica-Bold",
            size=11,
            color=CYAN
        )
        current_y -= 0.5*cm

        interest_words = simpleSplit(client_friendly, "Helvetica-Bold", 10, page_width - 4*cm)
        for line in interest_words:
            current_y -= 0.45*cm
            draw_text(line, 2*cm, current_y, font="Helvetica-Bold", size=10, color=GREEN)

        current_y -= 0.8*cm
        draw_section_line(current_y)
        current_y -= 0.6*cm

    posts = last_report.get('posts', [])
    top_posts = sorted(posts, key=lambda x: x.get('impact_score', 0), reverse=True)[:3]

    if top_posts:
        draw_text(
            "TOP 3 WINS THIS MONTH",
            2*cm,
            current_y,
            font="Helvetica-Bold",
            size=11,
            color=CYAN
        )
        current_y -= 0.5*cm

        max_score = max(p.get('impact_score', 1) for p in top_posts) or 1
        win_labels = ["01", "02", "03"]

        for i, post in enumerate(top_posts):
            if current_y < 4*cm:
                c.showPage()
                new_page()
                current_y = page_height - 2*cm
                draw_section_line(current_y)
                current_y -= 0.6*cm

            win_card_h = 2.2*cm
            win_card_y = current_y - win_card_h
            draw_card(2*cm, win_card_y, page_width - 4*cm, win_card_h, bg=CARD_BG, border=PURPLE, radius=6)

            draw_text(
                win_labels[i],
                2.4*cm,
                win_card_y + win_card_h - 0.6*cm,
                font="Helvetica-Bold",
                size=14,
                color=PURPLE
            )

            title = post.get('post_title', '')[:55]
            draw_text(
                title,
                3.4*cm,
                win_card_y + win_card_h - 0.6*cm,
                font="Helvetica-Bold",
                size=10,
                color=WHITE
            )

            rating = post.get('efficiency_rating', '')
            rating_color = GREEN if rating == "High-Value Content" else (RED if rating == "Low-Efficiency Growth" else AMBER)
            draw_text(
                rating.upper(),
                3.4*cm,
                win_card_y + 0.9*cm,
                font="Helvetica-Bold",
                size=8,
                color=rating_color
            )

            score_val = post.get('impact_score', 0)
            bar_w = page_width - 4*cm - 1.5*cm - 2.5*cm
            bar_x = 3.4*cm
            bar_y = win_card_y + 0.4*cm
            bar_percent = (score_val / max_score) * 100
            draw_progress_bar(bar_x, bar_y, bar_w, 0.2*cm, bar_percent, color=CYAN)

            score_text = f"Score: {score_val}"
            draw_text(
                score_text,
                page_width - 4*cm,
                win_card_y + win_card_h - 0.6*cm,
                font="Helvetica-Bold",
                size=9,
                color=CYAN
            )

            current_y = win_card_y - 0.3*cm

        current_y -= 0.5*cm

    if current_y < 4*cm:
        c.showPage()
        new_page()
        current_y = page_height - 2*cm

    draw_section_line(current_y)
    current_y -= 0.6*cm

    key_insights = last_report.get('key_insights', [])
    if key_insights:
        draw_text(
            "KEY TAKEAWAYS",
            2*cm,
            current_y,
            font="Helvetica-Bold",
            size=11,
            color=CYAN
        )
        current_y -= 0.5*cm

        for insight in key_insights:
            if current_y < 4*cm:
                c.showPage()
                new_page()
                current_y = page_height - 2*cm

            insight_lines = simpleSplit(f"— {insight}", "Helvetica", 10, page_width - 4.5*cm)
            for line in insight_lines:
                current_y -= 0.45*cm
                draw_text(line, 2.3*cm, current_y, font="Helvetica", size=10, color=WHITE)
            current_y -= 0.2*cm

        current_y -= 0.4*cm

    if current_y < 4*cm:
        c.showPage()
        new_page()
        current_y = page_height - 2*cm

    draw_section_line(current_y)
    current_y -= 0.6*cm

    next_month = last_report.get('next_month_vision', '')
    if next_month:
        draw_text(
            "WHAT WE'RE BUILDING TOWARD NEXT MONTH",
            2*cm,
            current_y,
            font="Helvetica-Bold",
            size=11,
            color=CYAN
        )
        current_y -= 0.5*cm

        next_lines = simpleSplit(next_month, "Helvetica", 10, page_width - 4*cm)
        for line in next_lines:
            current_y -= 0.45*cm
            draw_text(line, 2*cm, current_y, font="Helvetica", size=10, color=WHITE)

    draw_section_line(1.8*cm)
    set_color(MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(
        page_width / 2,
        1.2*cm,
        "Generated by Reportly · Confidential · For Client Use Only"
    )

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="client_report.pdf",
        mimetype="application/pdf"
    )

@app.route("/download/smm")
def download_smm():
    if not last_report:
        return "No report generated yet", 400

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import simpleSplit
    import io

    buffer = io.BytesIO()
    page_width, page_height = A4

    c = canvas.Canvas(buffer, pagesize=A4)

    MIDNIGHT = (18/255, 18/255, 18/255)
    CARD_BG = (30/255, 30/255, 30/255)
    CARD_LIGHT = (40/255, 40/255, 40/255)
    WHITE = (1, 1, 1)
    MUTED = (160/255, 160/255, 160/255)
    CYAN = (0/255, 255/255, 255/255)
    PURPLE = (191/255, 0/255, 255/255)
    GREEN = (74/255, 222/255, 128/255)
    AMBER = (251/255, 146/255, 60/255)
    RED = (248/255, 113/255, 113/255)
    BLUE = (59/255, 130/255, 246/255)

    def set_color(rgb):
        c.setFillColorRGB(*rgb)

    def set_stroke(rgb):
        c.setStrokeColorRGB(*rgb)

    def draw_background():
        set_color(MIDNIGHT)
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    def draw_card(x, y, w, h, bg=CARD_BG, border=PURPLE, radius=8):
        set_color(bg)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)
        set_stroke(border)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, fill=0, stroke=1)

    def draw_section_line(y, color=PURPLE):
        set_stroke(color)
        c.setLineWidth(0.5)
        c.line(2*cm, y, page_width - 2*cm, y)

    def draw_progress_bar(x, y, w, h, percent, color=CYAN, bg=CARD_LIGHT):
        set_color(bg)
        c.roundRect(x, y, w, h, 3, fill=1, stroke=0)
        filled_w = max(w * min(percent / 100, 1), 0)
        if filled_w > 0:
            set_color(color)
            c.roundRect(x, y, filled_w, h, 3, fill=1, stroke=0)

    def draw_text(text, x, y, font="Helvetica", size=11, color=WHITE):
        set_color(color)
        c.setFont(font, size)
        c.drawString(x, y, str(text))

    def draw_centered_text(text, y, font="Helvetica", size=11, color=WHITE):
        set_color(color)
        c.setFont(font, size)
        c.drawCentredString(page_width / 2, y, str(text))

    def check_page_break(y, threshold=4*cm):
        if y < threshold:
            c.showPage()
            draw_background()
            draw_header()
            return page_height - 2.5*cm
        return y

    def draw_header():
        set_color(PURPLE)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(2*cm, page_height - 1.2*cm, "REPORTLY")
        set_color(MUTED)
        c.setFont("Helvetica", 9)
        c.drawRightString(
            page_width - 2*cm,
            page_height - 1.2*cm,
            "INTERNAL · SMM TACTICAL REPORT"
        )
        draw_section_line(page_height - 1.5*cm)

    draw_background()
    draw_header()

    draw_centered_text(
        "SMM TACTICAL REPORT",
        page_height - 2.5*cm,
        font="Helvetica-Bold",
        size=20,
        color=WHITE
    )
    draw_centered_text(
        "Internal Use Only — Do Not Share With Client",
        page_height - 3.1*cm,
        font="Helvetica",
        size=9,
        color=RED
    )

    current_y = page_height - 3.8*cm
    draw_section_line(current_y)
    current_y -= 0.7*cm

    draw_text(
        "THE KILL LIST",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=13,
        color=RED
    )
    draw_text(
        "Posts to kill or completely rethink",
        8*cm,
        current_y,
        font="Helvetica",
        size=9,
        color=MUTED
    )
    current_y -= 0.5*cm

    kill_list = last_report.get('kill_list', [])
    for item in kill_list:
        current_y = check_page_break(current_y, 5*cm)

        card_h = 2.8*cm
        card_y = current_y - card_h
        draw_card(2*cm, card_y, page_width - 4*cm, card_h, bg=CARD_BG, border=RED, radius=6)

        set_color(RED)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(2.4*cm, card_y + card_h - 0.6*cm, "✕")

        title = item.get('post_title', '')[:55]
        draw_text(
            title,
            3.0*cm,
            card_y + card_h - 0.6*cm,
            font="Helvetica-Bold",
            size=10,
            color=WHITE
        )

        reason = item.get('reason', '')
        reason_lines = simpleSplit(f"Why: {reason}", "Helvetica", 9, page_width - 5.5*cm)
        reason_y = card_y + card_h - 1.1*cm
        for line in reason_lines:
            draw_text(line, 2.4*cm, reason_y, font="Helvetica", size=9, color=MUTED)
            reason_y -= 0.35*cm

        replacement = item.get('replacement', '')
        replacement_lines = simpleSplit(
            f"Replace with: {replacement}",
            "Helvetica-Bold",
            9,
            page_width - 5.5*cm
        )
        replace_y = card_y + 0.5*cm
        for line in replacement_lines:
            draw_text(line, 2.4*cm, replace_y, font="Helvetica-Bold", size=9, color=BLUE)
            replace_y -= 0.35*cm

        current_y = card_y - 0.4*cm

    current_y -= 0.3*cm
    current_y = check_page_break(current_y)
    draw_section_line(current_y)
    current_y -= 0.7*cm

    draw_text(
        "FORMAT VELOCITY",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=13,
        color=CYAN
    )
    current_y -= 0.5*cm

    format_velocity = last_report.get('format_velocity', '')
    if format_velocity:
        fv_lines = simpleSplit(format_velocity, "Helvetica", 10, page_width - 4*cm)
        for line in fv_lines:
            draw_text(line, 2*cm, current_y, font="Helvetica", size=10, color=WHITE)
            current_y -= 0.45*cm

    current_y -= 0.5*cm
    current_y = check_page_break(current_y)
    draw_section_line(current_y)
    current_y -= 0.7*cm

    draw_text(
        "SAVE-TO-REACH RATIO",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=13,
        color=CYAN
    )
    current_y -= 0.5*cm

    ratio_card_h = 1.8*cm
    ratio_card_y = current_y - ratio_card_h
    draw_card(2*cm, ratio_card_y, page_width - 4*cm, ratio_card_h, bg=CARD_BG, border=CYAN, radius=6)

    draw_text(
        f"Technical: {last_report.get('save_to_reach_ratio', 'N/A')}",
        2.4*cm,
        ratio_card_y + ratio_card_h - 0.6*cm,
        font="Helvetica-Bold",
        size=10,
        color=CYAN
    )
    draw_text(
        f"Meaning: {last_report.get('save_to_reach_client_friendly', '')}",
        2.4*cm,
        ratio_card_y + 0.5*cm,
        font="Helvetica",
        size=9,
        color=MUTED
    )

    current_y = ratio_card_y - 0.7*cm
    current_y = check_page_break(current_y)
    draw_section_line(current_y)
    current_y -= 0.7*cm

    draw_text(
        "POST PERFORMANCE BREAKDOWN",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=13,
        color=CYAN
    )
    current_y -= 0.6*cm

    posts = last_report.get('posts', [])
    sorted_posts = sorted(posts, key=lambda x: x.get('impact_score', 0), reverse=True)

    header_h = 0.55*cm
    header_y = current_y - header_h
    draw_card(2*cm, header_y, page_width - 4*cm, header_h, bg=CARD_LIGHT, border=PURPLE, radius=4)

    draw_text("POST", 2.3*cm, header_y + 0.15*cm, font="Helvetica-Bold", size=8, color=PURPLE)
    draw_text("SCORE", page_width - 6.5*cm, header_y + 0.15*cm, font="Helvetica-Bold", size=8, color=PURPLE)
    draw_text("RATING", page_width - 4.8*cm, header_y + 0.15*cm, font="Helvetica-Bold", size=8, color=PURPLE)
    current_y = header_y - 0.2*cm

    max_score = max((p.get('impact_score', 1) for p in sorted_posts), default=1) or 1

    for i, post in enumerate(sorted_posts):
        current_y = check_page_break(current_y, 3*cm)

        row_h = 0.9*cm
        row_y = current_y - row_h
        row_bg = CARD_BG if i % 2 == 0 else (25/255, 25/255, 25/255)
        draw_card(2*cm, row_y, page_width - 4*cm, row_h, bg=row_bg, border=PURPLE, radius=4)

        title = post.get('post_title', '')[:38]
        draw_text(title, 2.3*cm, row_y + 0.32*cm, font="Helvetica", size=8, color=WHITE)

        score_val = post.get('impact_score', 0)
        bar_w = 2.5*cm
        bar_x = page_width - 7.5*cm
        draw_progress_bar(bar_x, row_y + 0.3*cm, bar_w, 0.25*cm, (score_val / max_score) * 100, color=CYAN)
        draw_text(str(score_val), page_width - 6.4*cm, row_y + 0.32*cm, font="Helvetica-Bold", size=8, color=CYAN)

        rating = post.get('efficiency_rating', '')
        rating_color = GREEN if rating == "High-Value Content" else (RED if rating == "Low-Efficiency Growth" else AMBER)
        draw_text(rating[:18], page_width - 4.8*cm, row_y + 0.32*cm, font="Helvetica-Bold", size=7, color=rating_color)

        current_y = row_y - 0.15*cm

    current_y -= 0.5*cm
    current_y = check_page_break(current_y)
    draw_section_line(current_y)
    current_y -= 0.7*cm

    draw_text(
        "4-WEEK BATTLE PLAN",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=13,
        color=CYAN
    )
    current_y -= 0.5*cm

    battle_plan = last_report.get('battle_plan', [])
    week_colors = [CYAN, PURPLE, GREEN, AMBER]

    for i, action in enumerate(battle_plan):
        current_y = check_page_break(current_y, 3*cm)

        week_card_h = 1.4*cm
        week_card_y = current_y - week_card_h
        week_color = week_colors[i % len(week_colors)]
        draw_card(2*cm, week_card_y, page_width - 4*cm, week_card_h, bg=CARD_BG, border=week_color, radius=6)

        draw_text(
            f"WEEK {i+1}",
            2.4*cm,
            week_card_y + week_card_h - 0.55*cm,
            font="Helvetica-Bold",
            size=8,
            color=week_color
        )

        action_lines = simpleSplit(action, "Helvetica", 9, page_width - 6.5*cm)
        action_y = week_card_y + week_card_h - 0.55*cm
        for line in action_lines:
            draw_text(line, 4.2*cm, action_y, font="Helvetica", size=9, color=WHITE)
            action_y -= 0.38*cm

        current_y = week_card_y - 0.3*cm

    current_y -= 0.3*cm
    current_y = check_page_break(current_y)
    draw_section_line(current_y)
    current_y -= 0.7*cm

    draw_text(
        "OVERALL RECOMMENDATIONS",
        2*cm,
        current_y,
        font="Helvetica-Bold",
        size=13,
        color=CYAN
    )
    current_y -= 0.5*cm

    for rec in last_report.get('overall_recommendations', []):
        current_y = check_page_break(current_y, 2*cm)
        rec_lines = simpleSplit(f"→  {rec}", "Helvetica", 10, page_width - 4.5*cm)
        for line in rec_lines:
            draw_text(line, 2.3*cm, current_y, font="Helvetica", size=10, color=WHITE)
            current_y -= 0.45*cm
        current_y -= 0.2*cm

    draw_section_line(1.8*cm)
    set_color(MUTED)
    c.setFont("Helvetica", 8)
    c.drawCentredString(
        page_width / 2,
        1.2*cm,
        "Generated by Reportly · Internal SMM Report · Do Not Distribute"
    )

    c.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="smm_report.pdf",
        mimetype="application/pdf"
    )

@app.route("/fetch-instagram", methods=["POST"])
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
            return jsonify({
                "error": "No posts found or account is private"
            }), 404

        formatted_data = format_for_reportly(posts_data)
        return jsonify({
            "success": True,
            "posts_count": len(posts_data),
            "formatted_data": formatted_data,
            "raw_data": posts_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)