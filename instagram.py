import requests
import os
from datetime import datetime, timedelta


def get_access_token() -> str:
    return os.getenv("INSTAGRAM_ACCESS_TOKEN", "")


def get_ig_user_id() -> str:
    return os.getenv("INSTAGRAM_USER_ID", "")


def calculate_impact_score(likes: int, comments: int,
                            saves: int, shares: int) -> int:
    return (saves * 10) + (shares * 5) + (comments * 2) + (likes * 1)


def fetch_instagram_data(username: str = None) -> list:
    access_token = get_access_token()
    ig_user_id   = get_ig_user_id()

    if not access_token or not ig_user_id:
        print("Missing INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_USER_ID in environment.")
        return []

    posts_data = []
    cutoff     = datetime.utcnow() - timedelta(days=30)

    url    = f"https://graph.facebook.com/v26.0/{ig_user_id}/media"
    params = {
        "fields": (
            "id,timestamp,caption,media_type,"
            "like_count,comments_count,"
            "insights.metric(reach,impressions,saved,shares)"
        ),
        "access_token": access_token,
        "limit": 50,
    }

    while url:
        response = requests.get(url, params=params, timeout=15)

        if response.status_code != 200:
            print(f"API error {response.status_code}: {response.text}")
            break

        data  = response.json()
        posts = data.get("data", [])

        for post in posts:
            try:
                post_date = datetime.strptime(
                    post["timestamp"], "%Y-%m-%dT%H:%M:%S%z"
                ).replace(tzinfo=None)
            except Exception:
                continue

            if post_date < cutoff:
                url = None
                break

            caption    = post.get("caption", "No caption")
            media_type = post.get("media_type", "IMAGE")

            if media_type in ("VIDEO", "REELS"):
                post_type = "Reel"
            elif media_type == "CAROUSEL_ALBUM":
                post_type = "Carousel"
            else:
                post_type = "Image"

            likes    = post.get("like_count", 0) or 0
            comments = post.get("comments_count", 0) or 0

            reach       = 0
            impressions = 0
            saves       = 0
            shares      = 0

            insights = post.get("insights", {}).get("data", [])
            for metric in insights:
                name  = metric.get("name", "")
                value = metric.get("values", [{}])[0].get("value", 0) or 0
                if name == "reach":
                    reach = value
                elif name == "impressions":
                    impressions = value
                elif name == "saved":
                    saves = value
                elif name == "shares":
                    shares = value

            impact_score = calculate_impact_score(likes, comments, saves, shares)

            posts_data.append({
                "post_title":      (caption[:80] + "...") if len(caption) > 80 else caption,
                "post_type":       post_type,
                "date":            post_date.strftime("%Y-%m-%d"),
                "likes":           likes,
                "comments":        comments,
                "saves":           saves,
                "shares":          shares,
                "reach":           reach,
                "impressions":     impressions,
                "profile_visits":  0,
                "url_clicks":      0,
                "impact_score":    impact_score,
                "post_id":         post.get("id", ""),
                "url": f"https://www.instagram.com/p/{post.get('id', '')}/"
            })

        next_page = data.get("paging", {}).get("next")
        if next_page and url is not None:
            url    = next_page
            params = {}
        else:
            url = None

    print(f"Fetched {len(posts_data)} posts from Instagram Graph API")
    return posts_data


def format_for_reportly(posts_data: list) -> str:
    if not posts_data:
        return "No posts found in the last 30 days."

    reels     = [p for p in posts_data if p["post_type"] == "Reel"]
    images    = [p for p in posts_data if p["post_type"] == "Image"]
    carousels = [p for p in posts_data if p["post_type"] == "Carousel"]

    total_likes       = sum(p["likes"]       for p in posts_data)
    total_comments    = sum(p["comments"]    for p in posts_data)
    total_saves       = sum(p["saves"]       for p in posts_data)
    total_shares      = sum(p["shares"]      for p in posts_data)
    total_reach       = sum(p["reach"]       for p in posts_data)
    total_impressions = sum(p["impressions"] for p in posts_data)

    output  = "Instagram Analytics — Last 30 Days\n"
    output += "=" * 40 + "\n\n"
    output += f"Total posts: {len(posts_data)}\n"
    output += f"Reels: {len(reels)} | Images: {len(images)} | Carousels: {len(carousels)}\n"
    output += f"Total likes: {total_likes}\n"
    output += f"Total comments: {total_comments}\n"
    output += f"Total saves: {total_saves}\n"
    output += f"Total shares: {total_shares}\n"
    output += f"Total reach: {total_reach}\n"
    output += f"Total impressions: {total_impressions}\n\n"
    output += "POST BREAKDOWN\n"
    output += "-" * 40 + "\n\n"

    for i, post in enumerate(posts_data, 1):
        output += f"Post {i}: {post['post_title']}\n"
        output += f"Type: {post['post_type']}\n"
        output += f"Date: {post['date']}\n"
        output += f"Likes: {post['likes']}\n"
        output += f"Comments: {post['comments']}\n"
        output += f"Saves: {post['saves']}\n"
        output += f"Shares: {post['shares']}\n"
        output += f"Reach: {post['reach']}\n"
        output += f"Impressions: {post['impressions']}\n"
        output += f"Impact Score: {post['impact_score']}\n"
        output += f"URL: {post['url']}\n\n"

    return output


if __name__ == "__main__":
    data = fetch_instagram_data()
    if data:
        print(format_for_reportly(data))
    else:
        print("No data fetched. Check your environment variables.")