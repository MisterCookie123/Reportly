import instaloader
import itertools
import os
import json
from datetime import datetime, timedelta


CUSTOM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def load_session_from_json(username: str, L: instaloader.Instaloader) -> instaloader.Instaloader:
    cookie_file = "instagram_cookies.json"

    if not os.path.exists(cookie_file):
        print("instagram_cookies.json not found.")
        print("Export cookies from Chrome using EditThisCookie and save as instagram_cookies.json")
        return L

    try:
        with open(cookie_file, "r") as f:
            cookies = json.load(f)

        session_id = None

        for cookie in cookies:
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            domain = cookie.get("domain", ".instagram.com")

            if not domain.startswith("."):
                domain = "." + domain

            L.context._session.cookies.set(name, value, domain=domain)

            if name == "sessionid":
                session_id = value

        if session_id:
            print(f"Session ID found: {session_id[:10]}...")
            print("Cookies loaded successfully")
        else:
            print("WARNING: No sessionid cookie found.")
            print("Make sure you are logged into Instagram in Chrome before exporting cookies.")

    except Exception as e:
        print(f"Failed to load cookies: {e}")

    return L


def load_session(username: str) -> instaloader.Instaloader:
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

    L.context._session.headers.update({
        "User-Agent": CUSTOM_USER_AGENT
    })

    session_file = f"session-{username}"

    if os.path.exists(session_file):
        try:
            L.load_session_from_file(username, session_file)
            print(f"Session loaded from file for {username}")
            return L
        except Exception as e:
            print(f"Session file failed: {e} — trying cookie JSON")

    return load_session_from_json(username, L)


def calculate_impact_score(likes: int, comments: int) -> int:
    return (likes * 1) + (comments * 5)


def fetch_instagram_data(username: str) -> list:
    username = username.replace("@", "").strip()

    L = load_session(username)

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"Profile {username} does not exist")
        return []
    except instaloader.exceptions.LoginRequiredException:
        print(f"Profile {username} is private — login required")
        return []
    except Exception as e:
        print(f"Could not fetch profile {username}: {e}")
        return []

    posts_data = []
    cutoff_date = datetime.utcnow() - timedelta(days=30)

    try:
        posts = profile.get_posts()

        recent_posts = itertools.takewhile(
            lambda post: post.date_utc.replace(tzinfo=None) >= cutoff_date,
            posts
        )

        for post in recent_posts:
            post_type = "Reel" if post.is_video else "Image"

            view_count = 0
            if post.is_video:
                try:
                    view_count = post.video_view_count or 0
                except Exception:
                    view_count = 0

            likes = post.likes or 0
            comments_count = post.comments or 0
            impact_score = calculate_impact_score(likes, comments_count)

            post_data = {
                "post_title": (post.caption[:80] + "...") if post.caption and len(post.caption) > 80 else (post.caption or "No caption"),
                "post_type": post_type,
                "likes": likes,
                "comments": comments_count,
                "view_count": view_count,
                "saves": 0,
                "impact_score": impact_score,
                "date": post.date_utc.strftime("%Y-%m-%d"),
                "shortcode": post.shortcode,
                "url": f"https://www.instagram.com/p/{post.shortcode}/"
            }

            posts_data.append(post_data)
            print(f"Fetched: {post_data['post_title'][:40]} — Score: {impact_score}")

    except Exception as e:
        print(f"Error fetching posts: {e}")

    print(f"\nTotal posts fetched: {len(posts_data)}")
    return posts_data


def format_for_reportly(posts_data: list) -> str:
    if not posts_data:
        return "No posts found in the last 30 days."

    reels = [p for p in posts_data if p['post_type'] == 'Reel']
    images = [p for p in posts_data if p['post_type'] == 'Image']
    total_likes = sum(p['likes'] for p in posts_data)
    total_comments = sum(p['comments'] for p in posts_data)
    total_views = sum(p['view_count'] for p in posts_data)

    output = "Instagram Analytics — Last 30 Days\n"
    output += "=" * 40 + "\n\n"
    output += f"Total posts: {len(posts_data)}\n"
    output += f"Reels: {len(reels)} | Images: {len(images)}\n"
    output += f"Total likes: {total_likes}\n"
    output += f"Total comments: {total_comments}\n"
    if total_views:
        output += f"Total reel views: {total_views}\n"
    output += "\n"
    output += "POST BREAKDOWN\n"
    output += "-" * 40 + "\n\n"

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
        output += "\n"

    return output


if __name__ == "__main__":
    test_username = input("Enter Instagram username to test: ")
    print(f"\nFetching data for @{test_username}...\n")
    data = fetch_instagram_data(test_username)
    if data:
        formatted = format_for_reportly(data)
        print(formatted)
    else:
        print("No data fetched.")