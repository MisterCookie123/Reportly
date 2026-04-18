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

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    elements = []

    title_style = ParagraphStyle(
        'Title',
        fontSize=32,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#000000'),
        spaceAfter=6,
        alignment=TA_CENTER
    )
    tagline_style = ParagraphStyle(
        'Tagline',
        fontSize=12,
        fontName='Helvetica',
        textColor=colors.HexColor('#888888'),
        spaceAfter=4,
        alignment=TA_CENTER
    )
    section_style = ParagraphStyle(
        'Section',
        fontSize=15,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#000000'),
        spaceBefore=20,
        spaceAfter=10
    )
    body_style = ParagraphStyle(
        'Body',
        fontSize=11,
        fontName='Helvetica',
        textColor=colors.HexColor('#444444'),
        spaceAfter=6,
        leading=18
    )
    score_style = ParagraphStyle(
        'Score',
        fontSize=80,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#000000'),
        alignment=TA_CENTER,
        spaceAfter=0
    )
    score_label_style = ParagraphStyle(
        'ScoreLabel',
        fontSize=13,
        fontName='Helvetica',
        textColor=colors.HexColor('#888888'),
        alignment=TA_CENTER,
        spaceAfter=6
    )
    health_style = ParagraphStyle(
        'Health',
        fontSize=13,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#16a34a'),
        alignment=TA_CENTER,
        spaceAfter=24
    )
    win_title_style = ParagraphStyle(
        'WinTitle',
        fontSize=12,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#000000'),
        spaceAfter=3
    )
    win_body_style = ParagraphStyle(
        'WinBody',
        fontSize=11,
        fontName='Helvetica',
        textColor=colors.HexColor('#555555'),
        spaceAfter=12,
        leading=16
    )
    interest_style = ParagraphStyle(
        'Interest',
        fontSize=13,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#2563eb'),
        spaceAfter=4,
        alignment=TA_CENTER
    )
    footer_style = ParagraphStyle(
        'Footer',
        fontSize=9,
        fontName='Helvetica',
        textColor=colors.HexColor('#bbbbbb'),
        alignment=TA_CENTER
    )

    elements.append(Spacer(1, 1.5*cm))
    elements.append(Paragraph("Monthly Performance Report", title_style))
    elements.append(Paragraph("Prepared exclusively for you", tagline_style))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#eeeeee')))
    elements.append(Spacer(1, 0.8*cm))

    score = last_report.get('brand_health_score', 0)
    health = last_report.get('business_health', '')
    elements.append(Paragraph(str(score), score_style))
    elements.append(Paragraph("Brand Health Score", score_label_style))
    elements.append(Paragraph(f"Status: {health}", health_style))

    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#eeeeee')))
    elements.append(Spacer(1, 0.5*cm))

    elements.append(Paragraph("What We Achieved This Month", section_style))
    elements.append(Paragraph(last_report.get('executive_summary', ''), body_style))
    elements.append(Spacer(1, 0.3*cm))

    elements.append(Paragraph("Your Audience Is Paying Attention", section_style))
    elements.append(Paragraph(
        last_report.get('save_to_reach_client_friendly', ''),
        interest_style
    ))
    elements.append(Spacer(1, 0.3*cm))

    elements.append(Paragraph("Top 3 Wins This Month", section_style))
    posts = last_report.get('posts', [])
    top_posts = sorted(posts, key=lambda x: x.get('impact_score', 0), reverse=True)[:3]
    win_labels = ["First Win", "Second Win", "Third Win"]
    for i, post in enumerate(top_posts):
        elements.append(Paragraph(
            f"{win_labels[i]}: {post['post_title']}",
            win_title_style
        ))
        elements.append(Paragraph(
            f"This content delivered strong business value with an impact score of "
            f"{post['impact_score']} — rated {post['efficiency_rating']}.",
            win_body_style
        ))

    elements.append(Paragraph("Key Takeaways", section_style))
    for insight in last_report.get('key_insights', []):
        elements.append(Paragraph(f"— {insight}", body_style))

    elements.append(Spacer(1, 0.4*cm))
    elements.append(Paragraph("What We're Building Toward Next Month", section_style))
    elements.append(Paragraph(last_report.get('next_month_vision', ''), body_style))

    elements.append(Spacer(1, 1.5*cm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#eeeeee')))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        "Generated by Reportly · Confidential · For Client Use Only",
        footer_style
    ))

    doc.build(elements)
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

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        'Title',
        fontSize=24,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#000000'),
        spaceAfter=4,
        alignment=TA_CENTER
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        fontSize=11,
        fontName='Helvetica',
        textColor=colors.HexColor('#666666'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    section_style = ParagraphStyle(
        'Section',
        fontSize=13,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#000000'),
        spaceBefore=16,
        spaceAfter=8
    )
    body_style = ParagraphStyle(
        'Body',
        fontSize=10,
        fontName='Helvetica',
        textColor=colors.HexColor('#333333'),
        spaceAfter=5,
        leading=15
    )
    warning_style = ParagraphStyle(
        'Warning',
        fontSize=10,
        fontName='Helvetica',
        textColor=colors.HexColor('#cc0000'),
        spaceAfter=5,
        leading=15
    )

    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph("Reportly", title_style))
    elements.append(Paragraph("SMM Tactical Report — Internal Use Only", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#eeeeee')))
    elements.append(Spacer(1, 0.3*cm))

    elements.append(Paragraph("The Kill List", section_style))
    elements.append(Paragraph("Posts to kill or completely rethink:", body_style))
    for item in last_report.get('kill_list', []):
        elements.append(Paragraph(
            f"<b>✕ {item.get('post_title', '')}</b>",
            warning_style
        ))
        elements.append(Paragraph(
            f"Why it failed: {item.get('reason', '')}",
            body_style
        ))
        elements.append(Paragraph(
            f"Replace with: {item.get('replacement', '')}",
            ParagraphStyle(
                'Replace',
                fontSize=10,
                fontName='Helvetica-Bold',
                textColor=colors.HexColor('#2563eb'),
                spaceAfter=8,
                leading=15
            )
        ))
        elements.append(Spacer(1, 0.2 * cm))

    elements.append(Paragraph("Format Velocity", section_style))
    elements.append(Paragraph(last_report.get('format_velocity', ''), body_style))

    elements.append(Paragraph("Save-to-Reach Ratio", section_style))
    elements.append(Paragraph(
        f"Technical: {last_report.get('save_to_reach_ratio', '')}",
        body_style
    ))
    elements.append(Paragraph(
        f"What this means: {last_report.get('save_to_reach_client_friendly', '')}",
        body_style
    ))

    elements.append(Paragraph("Post Performance Breakdown", section_style))
    posts = last_report.get('posts', [])
    if posts:
        table_data = [['Post', 'Impact Score', 'Rating']]
        for post in sorted(posts, key=lambda x: x.get('impact_score', 0), reverse=True):
            table_data.append([
                post.get('post_title', '')[:40],
                str(post.get('impact_score', 0)),
                post.get('efficiency_rating', '')
            ])

        table = Table(table_data, colWidths=[9*cm, 3*cm, 5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#000000')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f9f9f9'), colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#eeeeee')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(table)

    elements.append(Paragraph("4-Week Battle Plan", section_style))
    for i, action in enumerate(last_report.get('battle_plan', []), 1):
        elements.append(Paragraph(f"Week {i}: {action}", body_style))

    elements.append(Paragraph("Overall Recommendations", section_style))
    for rec in last_report.get('overall_recommendations', []):
        elements.append(Paragraph(f"→ {rec}", body_style))

    elements.append(Spacer(1, 1*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#eeeeee')))
    elements.append(Paragraph(
        "Generated by Reportly — Internal SMM Report",
        ParagraphStyle('Footer', fontSize=9, textColor=colors.HexColor('#999999'), alignment=TA_CENTER)
    ))

    doc.build(elements)
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