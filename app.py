from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json.get("data", "")

    if not data:
        return jsonify({"error": "No data provided"}), 400

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """You are an expert social media strategist and analyst.

You will receive raw social media data. Your job is to analyze it deeply and return a JSON object only — no extra text, no markdown, no backticks.

Follow these rules strictly:

1. BUSINESS IMPACT SCORE
For each post calculate a BusinessImpactScore using these weights:
- Saves x10
- Shares x5
- Profile Visits x3
- Comments x2
- Likes x1
Higher score = higher business value.

2. CONVERSION EFFICIENCY
Calculate: (Profile Visits / Reach) * 100
If a post has high Reach but low Profile Visits and low Saves — flag it as "Low-Efficiency Growth"
If a post has high Saves relative to Reach — flag it as "High-Value Content"

3. STRATEGIC RECOMMENDATIONS
- If Save-to-Reach ratio is high → recommend "Create a 3-part series on this topic"
- If Views are high but URL Clicks are 0 or low → recommend "Improve your Call-to-Action (CTA)"
- If engagement is dropping over time → recommend "Audit your posting schedule and content mix"
- If video outperforms photos → recommend "Shift content calendar to 70% video"

4. OUTPUT FORMAT
Return a clean JSON object with this exact structure:

{
  "overall_summary": "2-3 sentences in plain language summarizing performance",
  "business_health": "Good / Needs Attention / Critical",
  "posts": [
    {
      "post_title": "name or description of the post",
      "impact_score": 0,
      "efficiency_rating": "High-Value Content / Low-Efficiency Growth / Average",
      "top_3_strategic_actions": [
        "Action 1",
        "Action 2", 
        "Action 3"
      ]
    }
  ],
  "top_performing_post": "title of best post",
  "worst_performing_post": "title of worst post",
  "key_insights": [
    "Insight 1 in plain language",
    "Insight 2 in plain language",
    "Insight 3 in plain language"
  ],
  "overall_recommendations": [
    "Recommendation 1",
    "Recommendation 2",
    "Recommendation 3"
  ]
}

Write all text as if explaining to a smart business owner who knows nothing about social media. No jargon. Be specific and direct."""
            },
            {
                "role": "user",
                "content": f"Analyze this social media data:\n\n{data}"
            }
        ]
    )

    raw = response.choices[0].message.content

    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        report = {"raw_output": raw}

    return jsonify({"report": report})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)