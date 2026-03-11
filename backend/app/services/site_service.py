import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.common.masking import mask_bot_config_inplace
from app.core.common.utils import Paginator, generate_token
from app.core.infra.config import settings
from app.core.integration.robot.services.dingtalk_app import DingTalkRobotService
from app.core.integration.robot.services.feishu_app import FeishuRobotService
from app.core.integration.robot.services.wecom_smart import WeComSmartService
from app.core.web.exceptions import BadRequestException, ConflictException, NotFoundException
from app.crud import crud_site, crud_user
from app.models.site import Site as SiteModel
from app.models.user import User, UserRole
from app.schemas.site import ClientSite, SiteCreate, SiteUpdate
from app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class SiteService:
    @staticmethod
    async def refresh_bot_stream_services() -> None:
        """站点机器人配置变更后，刷新飞书/钉钉/企微智能机器人长连接服务。"""
        try:
            await FeishuRobotService.get_instance().refresh()
        except Exception as e:
            logger.warning(f"刷新飞书长连接失败: {e}")
        try:
            await DingTalkRobotService.get_instance().refresh()
        except Exception as e:
            logger.warning(f"刷新钉钉 Stream 失败: {e}")
        try:
            await WeComSmartService.get_instance().refresh()
        except Exception as e:
            logger.warning(f"刷新企微智能机器人长连接失败: {e}")

    @staticmethod
    def ensure_bot_config_valid(bot_config: dict | None) -> None:
        """校验站点机器人配置，避免启用后静默失效。"""
        if not bot_config:
            return

        feishu = bot_config.get("feishu_app") or {}
        if feishu.get("enabled"):
            app_id = (feishu.get("app_id") or "").strip()
            app_secret = (feishu.get("app_secret") or "").strip()
            if not app_id or not app_secret:
                raise BadRequestException(
                    detail="启用飞书机器人时，App ID 和 App Secret 均不能为空。"
                )

        dingtalk = bot_config.get("dingtalk_app") or {}
        if not dingtalk.get("enabled"):
            return
        client_id = (dingtalk.get("client_id") or "").strip()
        client_secret = (dingtalk.get("client_secret") or "").strip()
        template_id = (dingtalk.get("template_id") or "").strip()
        if not client_id or not client_secret or not template_id:
            raise BadRequestException(
                detail="启用钉钉机器人时，Client ID、Client Secret、模板 ID 均不能为空。"
            )

        wecom_smart = bot_config.get("wecom_smart") or {}
        if wecom_smart.get("enabled"):
            if not wecom_smart.get("bot_id") or not wecom_smart.get("secret"):
                raise BadRequestException(
                    detail="启用企业微信智能机器人时，Bot ID 和 Secret 不能为空。"
                )

        wecom_kefu = bot_config.get("wecom_kefu") or {}
        if wecom_kefu.get("enabled"):
            if (
                not wecom_kefu.get("corp_id")
                or not wecom_kefu.get("secret")
                or not wecom_kefu.get("token")
                or not wecom_kefu.get("encoding_aes_key")
            ):
                raise BadRequestException(
                    detail="启用企业微信客服时，企业 ID、Secret、Token 和 Encoding AES Key 均不能为空。"
                )

        wecom_app = bot_config.get("wecom_app") or {}
        if wecom_app.get("enabled"):
            if (
                not wecom_app.get("corp_id")
                or not wecom_app.get("secret")
                or not wecom_app.get("token")
                or not wecom_app.get("encoding_aes_key")
            ):
                raise BadRequestException(
                    detail="启用企业微信机器人(应用)时，企业 ID、Secret、Token 和 Encoding AES Key 均不能为空。"
                )

    @staticmethod
    async def list_sites(
        db: AsyncSession, page: int, size: int, status: str | None, is_demo: bool
    ) -> tuple[list[SiteModel], Paginator]:
        """获取站点列表（分页）"""
        total = await crud_site.count(db, status=status)
        paginator = Paginator(page=page, size=size, total=total)

        stmt = select(SiteModel).options(joinedload(SiteModel.tenant))
        if status:
            stmt = stmt.where(SiteModel.status == status)

        result = await db.execute(stmt.offset(paginator.skip).limit(paginator.size))
        sites = list(result.scalars())

        if is_demo:
            for s in sites:
                if s.bot_config:
                    mask_bot_config_inplace(s.bot_config)
            logger.info(f"🔒 [Sites] Demo Mode: Masked {len(sites)} sites' bot config")

        return sites, paginator

    @staticmethod
    async def get_site(db: AsyncSession, site_id: int, is_demo: bool) -> SiteModel:
        """获取站点详情"""
        stmt = (
            select(SiteModel).where(SiteModel.id == site_id).options(joinedload(SiteModel.tenant))
        )
        result = await db.execute(stmt)
        site = result.scalar_one_or_none()
        if not site:
            raise NotFoundException(detail=f"站点 {site_id} 不存在")

        if is_demo:
            if site.bot_config:
                mask_bot_config_inplace(site.bot_config)
            logger.info(f"🔒 [Sites] Demo Mode: Masked bot config for site {site_id}")

        return site

    @staticmethod
    async def get_site_by_slug(db: AsyncSession, slug: str, is_demo: bool) -> SiteModel:
        """通过 slug 获取站点详情"""
        stmt = select(SiteModel).where(SiteModel.slug == slug).options(joinedload(SiteModel.tenant))
        result = await db.execute(stmt)
        site = result.scalar_one_or_none()
        if not site:
            raise NotFoundException(detail=f"站点 {slug} 不存在")

        if is_demo:
            if site.bot_config:
                mask_bot_config_inplace(site.bot_config)
            logger.info(f"🔒 [Sites] Demo Mode: Masked bot config for site slug={slug}")

        return site

    @staticmethod
    async def create_site(db: AsyncSession, site_in: SiteCreate) -> SiteModel:
        # 检查名称是否已存在
        existing = await crud_site.get_by_name(db, name=site_in.name)
        if existing:
            raise ConflictException(detail=f"站点名称 '{site_in.name}' 已存在")

        # 检查标识是否已存在
        if site_in.slug:
            existing_slug = await crud_site.get_by_slug(db, slug=site_in.slug)
            if existing_slug:
                raise ConflictException(detail=f"标识 '{site_in.slug}' 已存在")

        # 处理机器人配置：如果启用 API Bot 且没填 Key，自动生成一个
        if site_in.bot_config:
            SiteService.ensure_bot_config_valid(site_in.bot_config)
            api_bot = site_in.bot_config.get("api_bot")
            # CE 版本不支持 API Bot（企业版专属功能）
            if api_bot and settings.CATWIKI_EDITION == "community":
                api_bot["enabled"] = False
            elif api_bot and api_bot.get("enabled") and not api_bot.get("api_key"):
                api_bot["api_key"] = f"sk-{generate_token(24)}"

        # 先完成管理员参数与用户状态校验，避免后续报错时站点已创建
        admin_email: str | None = None
        admin_password: str | None = None
        existing_user: User | None = None
        if site_in.admin_email:
            admin_email = site_in.admin_email.lower().strip()
            existing_user = await crud_user.get_by_email(db, email=admin_email)
            if not existing_user:
                admin_password = (site_in.admin_password or "").strip()
                if not admin_password:
                    raise BadRequestException(
                        detail="提供管理员邮箱时，必须同时提供管理员密码（至少 8 位）。"
                    )

        try:
            site = await crud_site.create(db, obj_in=site_in, auto_commit=False)

            # 如果提供了管理员信息，初始化站点管理员
            if admin_email:
                if existing_user:
                    # 用户已存在，追加站点管理权限
                    current_managed_sites = existing_user.managed_sites
                    if site.id not in current_managed_sites:
                        new_managed_sites = current_managed_sites + [site.id]
                        await crud_user.update(
                            db,
                            db_obj=existing_user,
                            obj_in=UserUpdate(
                                managed_site_ids=new_managed_sites, role=existing_user.role
                            ),
                            auto_commit=False,
                        )
                else:
                    # 用户不存在，创建新用户
                    await crud_user.create(
                        db,
                        obj_in=UserCreate(
                            email=admin_email,
                            password=admin_password or "",
                            name=site_in.admin_name or admin_email.split("@")[0],
                            role=UserRole.SITE_ADMIN,
                            managed_site_ids=[site.id],
                        ),
                        auto_commit=False,
                    )

            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # 预加载租户信息以填充 tenant_slug
        await db.refresh(site, ["tenant"])

        await SiteService.refresh_bot_stream_services()
        return site

    @staticmethod
    async def update_site(db: AsyncSession, site_id: int, site_in: SiteUpdate) -> SiteModel:
        site = await crud_site.get(db, id=site_id)
        if not site:
            raise NotFoundException(detail=f"站点 {site_id} 不存在")

        # 检查名称冲突
        if site_in.name:
            existing = await crud_site.get_by_name(db, name=site_in.name)
            if existing and existing.id != site_id:
                raise ConflictException(detail=f"站点名称 '{site_in.name}' 已存在")

        # 检查标识冲突
        if site_in.slug:
            existing_slug = await crud_site.get_by_slug(db, slug=site_in.slug)
            if existing_slug and existing_slug.id != site_id:
                raise ConflictException(detail=f"标识 '{site_in.slug}' 已存在")

        # 处理机器人配置：如果启用 API Bot 且没填 Key，尝试沿用旧的或生成新的
        if site_in.bot_config:
            SiteService.ensure_bot_config_valid(site_in.bot_config)
            api_bot = site_in.bot_config.get("api_bot")
            # CE 版本不支持 API Bot（企业版专属功能）
            if api_bot and settings.CATWIKI_EDITION == "community":
                api_bot["enabled"] = False
            elif api_bot and api_bot.get("enabled") and not api_bot.get("api_key"):
                # 尝试从原有配置中获取
                old_bot_config = site.bot_config or {}
                old_api_bot = old_bot_config.get("api_bot")
                if old_api_bot and old_api_bot.get("api_key"):
                    api_bot["api_key"] = old_api_bot["api_key"]
                else:
                    # 原来也没有，生成一个新的
                    api_bot["api_key"] = f"sk-{generate_token(24)}"

        site = await crud_site.update(db, db_obj=site, obj_in=site_in)
        # 预加载租户信息以填充 tenant_slug
        await db.refresh(site, ["tenant"])
        await SiteService.refresh_bot_stream_services()
        return site

    @staticmethod
    async def delete_site(db: AsyncSession, site_id: int) -> None:
        # 1. 清理向量数据库中的数据
        # 为了保证数据完整性，必须先查询出该站点下的所有文档ID
        from app.models.document import Document

        # 查找站点下所有已向量化的文档或者所有文档（为了安全起见，查所有可能存在的文档）
        # 这里我们只关心 ID
        result = await db.execute(select(Document.id).where(Document.site_id == site_id))
        document_ids = list(result.scalars())

        if document_ids:
            try:
                from app.core.vector.vector_store import VectorStoreManager

                vector_store = await VectorStoreManager.get_instance()

                # 逐个文档清理向量（因为每个文档可能有多个 chunk）
                for doc_id in document_ids:
                    await vector_store.delete_by_metadata(key="id", value=str(doc_id))

                logger.info(f"✅ 已清理站点 {site_id} 下 {len(document_ids)} 个文档的向量数据")
            except Exception as e:
                # 记录错误但不中断删除流程（或者根据需求决定是否中断）
                # 这里选择不中断，因为站点删除是主要意图，向量残留是次要问题（虽然我们要修复它，但不能阻止用户删除）
                # 也可以选择 log error
                logger.warning(f"清理站点 {site_id} 的向量数据失败: {e}")

        # 2. 删除数据库数据
        success = await crud_site.remove_with_relationships(db, id=site_id)
        if not success:
            raise NotFoundException(detail=f"站点 {site_id} 不存在")

        await SiteService.refresh_bot_stream_services()

    @staticmethod
    async def list_client_sites(
        db: AsyncSession,
        page: int,
        size: int,
        tenant_id: int | None,
        tenant_slug: str | None,
        keyword: str | None,
    ) -> tuple[list[ClientSite], Paginator]:
        """获取激活的站点列表（客户端）"""
        from sqlalchemy import func, or_, select

        # 构建基础查询条件
        base_filters = [SiteModel.status == "active"]
        if tenant_id is not None:
            base_filters.append(SiteModel.tenant_id == tenant_id)
        elif tenant_slug:
            from app.models.tenant import Tenant as TenantModel

            # 通过 Join 租户表过滤
            stmt_tenant = select(TenantModel.id).where(TenantModel.slug == tenant_slug)
            tenant_id_res = (await db.execute(stmt_tenant)).scalar_one_or_none()
            if tenant_id_res:
                base_filters.append(SiteModel.tenant_id == tenant_id_res)
            else:
                return [], Paginator(page=page, size=size, total=0)

        if keyword:
            base_filters.append(
                or_(
                    SiteModel.name.icontains(keyword),
                    SiteModel.description.icontains(keyword),
                )
            )

        # 统计总数
        count_stmt = select(func.count()).select_from(SiteModel).where(*base_filters)
        total = (await db.execute(count_stmt)).scalar_one()
        paginator = Paginator(page=page, size=size, total=total)

        # 查询站点列表，预加载租户信息
        stmt = select(SiteModel).where(*base_filters).options(joinedload(SiteModel.tenant))
        result = await db.execute(stmt.offset(paginator.skip).limit(paginator.size))
        sites = list(result.scalars())

        # [Security] 使用 ClientSite Schema 自动过滤敏感字段
        client_sites = [ClientSite.model_validate(site, from_attributes=True) for site in sites]
        return client_sites, paginator

    @staticmethod
    async def get_client_site(
        db: AsyncSession, site_id: int | None = None, slug: str | None = None
    ) -> ClientSite:
        """获取激活的站点详情（客户端）"""
        from sqlalchemy import select

        if site_id:
            stmt = select(SiteModel).where(SiteModel.id == site_id)
        else:
            stmt = select(SiteModel).where(SiteModel.slug == slug)

        stmt = stmt.options(joinedload(SiteModel.tenant))
        result = await db.execute(stmt)
        site = result.scalar_one_or_none()
        if not site or site.status != "active":
            raise NotFoundException(detail=f"站点 {site_id or slug} 不存在")

        return ClientSite.model_validate(site, from_attributes=True)
