from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import current_user
from app.services.tools_service import list_tools

router = APIRouter(dependencies=[Depends(current_user)])


class ToolOut(BaseModel):
    slug: str
    title: str
    description: str
    prompt_prefix: str
    recommended_category: str
    # 3-сек превью-луп карточки; файл лежит в frontend public/trends/<slug>.mp4
    # (фронт резолвит по своему origin). Единый шаблон -- имя = slug.
    preview_url: str


@router.get("/tools", response_model=list[ToolOut])
async def get_tools() -> list[ToolOut]:
    return [ToolOut(**vars(t), preview_url=f"/trends/{t.slug}.mp4") for t in list_tools()]
