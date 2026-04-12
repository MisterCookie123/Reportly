from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
import os

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
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": """You are an expert social media analyst. 
                You will receive raw social media performance data.
                Generate a clear client report with exactly this structure:

                SUMMARY
                One paragraph in plain language summarizing overall performance.

                KEY INSIGHTS
                3-5 bullet points of what the data actually means. No jargon.

                WHAT IS WORKING
                2-3 specific things performing well and why.

                WHAT NEEDS IMPROVEMENT
                2-3 specific things underperforming and why.

                RECOMMENDATIONS
                3 specific actionable next steps the client should take.

                Write as if explaining to a smart business owner who knows 
                nothing about social media metrics. Never use jargon."""
            },
            {
                "role": "user",
                "content": f"Here is the social media data to analyze:\n\n{data}"
            }
        ]
    )

    report = response.choices[0].message.content
    return jsonify({"report": report})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)