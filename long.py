from fastapi import APIRouter, Request, Header, HTTPException
from typing import Optional, List
from fastapi.responses import RedirectResponse, JSONResponse
import httpx
from sqlalchemy.orm import Session

# schemas.py 파일에서 정의한 Pydantic 모델들을 가져옵니다.
from domain.user.schemas import *
from database import get_db
from models import User
from domain.user.webhook_handler import (
    WebhookHandler,
    save_webhook_info,
    delete_webhook_info, get_current_user, get_user_access_token
)
from app.config import (
    GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_AUTH_URL,
    GITHUB_TOKEN_URL, GITHUB_API_URL, GITHUB_WEBHOOK_SECRET
)

# 태그(tags)를 기능별로 분리하여 API를 그룹화합니다.
# main.py에서 태그에 대한 설명을 추가하면 더 상세한 문서화가 가능합니다.
router = APIRouter(prefix="/github")


# --- Authentication ---

@router.get(
    "/auth/login",
    tags=["Authentication"],
    summary="GitHub OAuth 로그인 시작",
    description="사용자를 GitHub OAuth 인증 페이지로 리디렉션하여 로그인을 시작합니다."
)
def login():
    """GitHub OAuth 로그인 시작"""
    scopes = "read:user,admin:repo_hook,repo"
    # 사용자가 GitHub에서 인증을 완료하면, GitHub 앱에 등록된 'Authorization callback URL'로 리디렉션됩니다.
    # 이 URL을 프론트엔드의 특정 경로로 설정해야 합니다. (예: https://your-frontend.com/auth/github)
    redirect_url = f"{GITHUB_AUTH_URL}?client_id={GITHUB_CLIENT_ID}&scope={scopes}"
    return RedirectResponse(redirect_url)


@router.get(
    "/auth/callback",
    tags=["Authentication"],
    summary="GitHub OAuth 콜백 처리",
    description="프론트엔드로부터 GitHub 인증 코드를 받아 액세스 토큰을 요청하고, 토큰과 사용자 정보를 반환합니다."
)
async def callback(code: str):
    """
    프론트엔드에서 전달받은 code를 사용하여 GitHub 액세스 토큰을 요청하고,
    토큰과 사용자 정보를 프론트엔드로 반환합니다.
    """
    async with httpx.AsyncClient() as client:
        # 1. 전달받은 code로 Access Token 요청
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
        )
        token_data = token_response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="GitHub OAuth failed: Could not retrieve access token.")

        # 2. Access Token으로 사용자 정보 요청
        user_response = await client.get(
            GITHUB_API_URL,
            headers={"Authorization": f"token {access_token}"},
        )
        user_data = user_response.json()

        # 여기서 기존의 사용자 정보 DB 저장/업데이트 로직을 수행할 수 있습니다.


    # 사용자 정보 데이터베이스에 저장
    db: Session = next(get_db())
    try:
        existing_user = db.query(User).filter_by(github_id=user_data["id"]).first()
        if existing_user:
            existing_user.access_token = access_token
            existing_user.email = user_data.get("email")
            db.commit()
            user_record = existing_user
        else:
            new_user = User(
                github_id=user_data["id"],
                username=user_data["login"],
                email=user_data.get("email"),
                access_token=access_token
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            user_record = new_user

        # 성공 응답 반환
        return JSONResponse(status_code=200, content={
            "message": "Login successful",
            "user": {
                "id": user_record.id,
                "github_id": user_record.github_id,
                "username": user_record.username,
                "email": user_record.email
            },
            "access_token": access_token
        })
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save user: {str(e)}")
    finally:
        db.close()


# --- Repositories ---

@router.get(
    "/repositories/{user_id}",
    tags=["Repositories"],
    response_model=RepositoriesResponse,
    summary="사용자의 GitHub 저장소 목록 조회",
    description="사용자 ID를 기반으로 해당 사용자가 'admin' 권한을 가진 모든 저장소 목록을 조회합니다."
)
async def get_user_repositories(user_id: int):
    """사용자의 GitHub 저장소 목록 조회"""
    try:
        user = await get_current_user(user_id)
        access_token = await get_user_access_token(user)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": f"token {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={"type": "owner", "sort": "updated", "per_page": 100}
            )

            if response.status_code == 200:
                repos = response.json()
                admin_repos = [
                    RepositoryInfo(
                        name=repo["name"],
                        full_name=repo["full_name"],
                        private=repo["private"],
                        default_branch=repo["default_branch"],
                        permissions=repo["permissions"]
                    )
                    for repo in repos if repo.get("permissions", {}).get("admin")
                ]
                return RepositoriesResponse(
                    success=True,
                    repositories=admin_repos,
                    total=len(admin_repos)
                )
            else:
                return RepositoriesResponse(success=False,
                                                    error=f"Failed to fetch repositories: {response.status_code}")
    except Exception as e:
        return RepositoriesResponse(success=False, error=str(e))
