import instaloader
from datetime import datetime, timedelta
import os
import json


def load_session_from_file(username: str) -> instaloader.Instaloader:
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True
    )

    session_file = f"session-{username}"

    if os.path.exists(session_file):
        try:
            L.load_session_from_file(username, session_file)
            print(f"Session loaded for {username}")
            return L
        except Exception as e:
            print(f"Session load failed: {e}")

    instagram_username = os.getenv("INSTAGRAM_USERNAME")
    instagram_password = os.getenv("INSTAGRAM_PASSWORD")

    if instagram_username and instagram_password:
        try:
            L.login(instagram_username, instagram_password)
            L.save_session_to_file(session_file)
            print(f"Logged in and session saved for {username}")
        except Exception as e:
            print(f"Login failed: {e}")

    return L


def calculate_impact_score(likes: int, comments: int) -> int:
    return (likes * 1) + (comments * 5)


def fetch_instagram_data(username: str) -> list:
    L = load_session_from_file(username)

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        print(f"Could not fetch profile: {e}")
        return []

    posts_data = []
    cutoff_date = datetime.now() - timedelta(days=30)

    try:
        for post in profile.get_posts():
            if post.date_utc < cutoff_date:
                break

            if post.date_utc < cutoff_date:
                continue

            post_type = "Reel" if post.is_video and post.video_view_count else "Image"

            view_count = 0
            if post.is_video:
                try:
                    view_count = post.video_view_count or 0
                except Exception:
                    view_count = 0

            likes = post.likes or 0
            comments = post.comments or 0

            impact_score = calculate_impact_score(likes, comments)

            post_data = {
                "post_title": post.caption[:80] if post.caption else "No caption",
                "post_type": post_type,
                "likes": likes,
                "comments": comments,
                "view_count": view_count,
                "impact_score": impact_score,
                "date": post.date_utc.strftime("%Y-%m-%d"),
                "shortcode": post.shortcode,
                "url": f"https://www.instagram.com/p/{post.shortcode}/"
            }

            posts_data.append(post_data)

    except Exception as e:
        print(f"Error fetching posts: {e}")

    print(f"Fetched {len(posts_data)} posts for {username}")
    return posts_data


def format_for_reportly(posts_data: list) -> str:
    if not posts_data:
        return "No posts found in the last 30 days."

    output = f"Instagram Data — Last 30 Days\n"
    output += f"Total posts analyzed: {len(posts_data)}\n\n"

    for i, post in enumerate(posts_data, 1):
        output += f"Post {i}: {post['post_title']}\n"
        output += f"Type: {post['post_type']}\n"
        output += f"Date: {post['date']}\n"
        output += f"Likes: {post['likes']}\n"
        output += f"Comments: {post['comments']}\n"
        if post['view_count']:
            output += f"Views: {post['view_count']}\n"
        output += f"Impact Score: {post['impact_score']}\n"
        output += f"URL: {post['url']}\n"
        output += "---\n"

    return output


if __name__ == "__main__":
    test_username = "instagram"
    data = fetch_instagram_data(test_username)
    formatted = format_for_reportly(data)
    print(formatted)