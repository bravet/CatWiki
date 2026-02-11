// Copyright 2024 CatWiki Authors
// 
// Licensed under the CatWiki Open Source License (Modified Apache 2.0);
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     https://github.com/CatWiki/CatWiki/blob/main/LICENSE
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { useRouter, useSearchParams, usePathname } from "next/navigation"
import {
  Globe,
  Plus,
  Search,
  MoreHorizontal,
  Edit2,
  Trash2,
  ChevronLeft,
  X,
  Save,
  Loader2,
  Building2,
  Users,
  Play,
  Pause,
  Disc,
  ArrowLeft,
  Info,
  UserCog,
  CreditCard,
  HardDrive,
  Mail,
  Phone,
  LayoutGrid
} from "lucide-react"
import { getUserInfo, setSelectedTenantId } from "@/lib/auth"
import { UserRole } from "@/lib/api-client"
import api, { Models } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Badge } from "@/components/ui/badge"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ImageUpload } from "@/components/ui/ImageUpload"

// 订阅计划配置 - 不同计划对应不同资源配额
const PLAN_CONFIGS: Record<string, { name: string; max_sites: number; max_documents: number; max_storage_mb: number; max_users: number }> = {
  starter: {
    name: "入门版",
    max_sites: 3,
    max_documents: 1000,
    max_storage_mb: 1024,
    max_users: 10,
  },
  professional: {
    name: "专业版",
    max_sites: 10,
    max_documents: 5000,
    max_storage_mb: 10240,
    max_users: 50,
  },
  enterprise: {
    name: "企业版",
    max_sites: 50,
    max_documents: 100000,
    max_storage_mb: 102400,
    max_users: 500,
  },
}

export function PlatformModal() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const [mounted, setMounted] = useState(false)
  const [activeTab, setActiveTab] = useState("tenants")
  const [view, setView] = useState<"list" | "new" | "edit">("list")
  const [editingTenantId, setEditingTenantId] = useState<number | null>(null)

  // 表单状态整合
  const [formData, setFormData] = useState({
    name: "",
    slug: "",
    description: "",
    logo_url: "",
    plan: "starter",
    status: "active",
    max_sites: PLAN_CONFIGS.starter.max_sites,
    max_documents: PLAN_CONFIGS.starter.max_documents,
    max_storage_mb: PLAN_CONFIGS.starter.max_storage_mb,
    max_users: PLAN_CONFIGS.starter.max_users,
    contact_email: "",
    contact_phone: "",
    plan_expires_at: new Date(Date.now() + 31536000000).toISOString().split('T')[0], // 默认一年后
    isSubmitting: false
  })

  useEffect(() => {
    setMounted(true)
  }, [])

  const userInfo = mounted ? getUserInfo() : null
  const isAdmin = userInfo?.role === UserRole.ADMIN

  const handleClose = () => {
    const params = new URLSearchParams(searchParams.toString())
    params.delete("modal")
    router.replace(`${pathname}?${params.toString()}`, { scroll: false })
  }

  const handleSave = async () => {
    if (!formData.name.trim()) return toast.error("请输入租户名称")
    if (!formData.slug.trim()) return toast.error("请输入唯一标识")

    setFormData(prev => ({ ...prev, isSubmitting: true }))
    try {
      const payload: any = {
        name: formData.name.trim(),
        slug: formData.slug.trim(),
        description: formData.description.trim() || undefined,
        logo_url: formData.logo_url || undefined,
        plan: formData.plan,
        status: formData.status,
        max_sites: Number(formData.max_sites),
        max_documents: Number(formData.max_documents),
        max_storage_mb: Number(formData.max_storage_mb),
        max_users: Number(formData.max_users),
        contact_email: formData.contact_email || undefined,
        contact_phone: formData.contact_phone || undefined,
        plan_expires_at: new Date(formData.plan_expires_at).toISOString(),
      }

      if (view === "new") {
        await api.tenant.create(payload)
        toast.success("新租户已成功开通")
      } else {
        await api.tenant.update(editingTenantId!, payload)
        toast.success("租户配置已更新")
      }
      setView("list")
    } catch (e: any) {
      toast.error(e.message || "操作失败，请重试")
    } finally {
      setFormData(prev => ({ ...prev, isSubmitting: false }))
    }
  }

  if (!mounted) return null
  if (!isAdmin) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 md:p-8 animate-in fade-in duration-300">
      <div className="w-full max-w-6xl h-[85vh] min-h-[600px] bg-white rounded-2xl shadow-2xl shadow-black/20 border border-slate-200/60 overflow-hidden flex flex-col animate-in slide-in-from-bottom-4 zoom-in-95 duration-300">

        {/* Window Header */}
        <div className="h-16 border-b border-slate-100 flex items-center justify-between px-6 shrink-0 bg-white">
          <div className="flex items-center gap-3">
            {view !== "list" ? (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setView("list")}
                className="h-8 w-8 rounded-lg -ml-2 text-slate-500 hover:text-slate-900"
              >
                <ChevronLeft className="h-5 w-5" />
              </Button>
            ) : (
              <div className="p-2 bg-slate-100 rounded-lg text-slate-600">
                <Globe className="h-5 w-5" />
              </div>
            )}
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">
                {view === "list" ? "系统设置" : view === "new" ? "创建租户" : "编辑租户"}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {view !== "list" && (
              <Button
                onClick={handleSave}
                disabled={formData.isSubmitting}
                className="flex items-center gap-2 h-8 px-4 text-xs rounded-full shadow-sm animate-in fade-in zoom-in duration-300"
              >
                {formData.isSubmitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                {view === "new" ? "开通租户" : "保存配置"}
              </Button>
            )}

            <div className="h-4 w-px bg-slate-200 mx-1" />

            <Button
              variant="ghost"
              size="icon"
              onClick={handleClose}
              className="h-8 w-8 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-900 transition-colors"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Window Body */}
        <Tabs value={activeTab} onValueChange={setActiveTab} orientation="vertical" className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <TabsList className="w-64 h-full bg-slate-50/50 border-r border-slate-100 flex-col items-stretch justify-start p-4 space-y-1">
            <TabsTrigger
              value="tenants"
              className={cn(
                "w-full justify-start px-3 py-2.5 h-auto text-sm font-medium rounded-lg transition-all",
                "data-[state=active]:bg-white data-[state=active]:text-primary data-[state=active]:shadow-sm data-[state=active]:ring-1 data-[state=active]:ring-slate-200",
                "hover:bg-white/60 hover:text-slate-900 text-slate-500"
              )}
              onClick={() => setView("list")}
            >
              <Building2 className="h-4 w-4 mr-3 opacity-70" />
              租户管理
            </TabsTrigger>
          </TabsList>

          {/* Content Area */}
          <div className="flex-1 overflow-y-auto bg-white relative">
            <div className="max-w-4xl mx-auto p-8 h-full">
              <TabsContent value="tenants" className="mt-0 h-full outline-none">
                {view === "list" && (
                  <TenantDashboard
                    onNew={() => {
                      setFormData({
                        name: "",
                        slug: "",
                        description: "",
                        logo_url: "",
                        plan: "starter",
                        status: "active",
                        max_sites: PLAN_CONFIGS.starter.max_sites,
                        max_documents: PLAN_CONFIGS.starter.max_documents,
                        max_storage_mb: PLAN_CONFIGS.starter.max_storage_mb,
                        max_users: PLAN_CONFIGS.starter.max_users,
                        contact_email: "",
                        contact_phone: "",
                        plan_expires_at: new Date(Date.now() + 31536000000).toISOString().split('T')[0],
                        isSubmitting: false
                      })
                      setView("new")
                    }}
                    onEdit={(id) => {
                      setEditingTenantId(id)
                      setView("edit")
                    }}
                  />
                )}
                {(view === "new" || view === "edit") && (
                  <TenantForm
                    tenantId={view === "edit" ? editingTenantId : undefined}
                    data={formData}
                    onChange={(newData) => setFormData(prev => ({ ...prev, ...newData }))}
                  />
                )}
              </TabsContent>
            </div>
          </div>
        </Tabs>
      </div>
    </div>
  )
}

function TenantDashboard({ onNew, onEdit }: { onNew: () => void, onEdit: (id: number) => void }) {
  const [tenants, setTenants] = useState<Models.TenantSchema_[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")

  const fetchTenants = async () => {
    setIsLoading(true)
    try {
      const data = await api.tenant.list({ size: 100 })
      setTenants(data.list)
    } catch (error) {
      console.error("Failed to fetch tenants:", error)
      toast.error("加载租户列表失败")
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchTenants()
  }, [])

  const filteredTenants = tenants.filter(tenant =>
    tenant.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    tenant.slug.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const stats = useMemo(() => {
    return {
      total: tenants.length,
      active: tenants.filter(t => t.status === 'active').length,
      storage: Math.round(tenants.reduce((acc, t) => acc + (t.max_storage_mb || 0), 0) / 1024),
      users: tenants.reduce((acc, t) => acc + (t.max_users || 0), 0)
    }
  }, [tenants])

  const handleDeleteTenant = async (id: number, name: string) => {
    if (!confirm(`确定要删除租户 "${name}" 吗?`)) return
    try {
      await api.tenant.delete(id)
      toast.success("租户已删除")
      fetchTenants()
    } catch (e) {
      toast.error("删除失败")
    }
  }

  const handleSwitchTenant = (id: number) => {
    setSelectedTenantId(id)
    window.location.reload()
  }

  const statusColors: Record<string, string> = {
    active: "bg-emerald-500/10 text-emerald-600 shadow-sm shadow-emerald-500/10 border-emerald-500/20",
    trial: "bg-blue-500/10 text-blue-600 shadow-sm shadow-blue-500/10 border-blue-500/20",
    disabled: "bg-slate-200 text-slate-500",
  }

  const planColors: Record<string, string> = {
    starter: "bg-slate-100 text-slate-600",
    professional: "bg-blue-100 text-blue-600",
    enterprise: "bg-purple-100 text-purple-600",
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300 pb-8">
      {/* 头部统计卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "总租户数", value: stats.total, icon: Building2, color: "text-slate-600", bg: "bg-slate-100" },
          { label: "活跃租户", value: stats.active, icon: Play, color: "text-emerald-600", bg: "bg-emerald-100" },
          { label: "总存储配额", value: `${stats.storage} GB`, icon: Disc, color: "text-blue-600", bg: "bg-blue-100" },
          { label: "总用户配额", value: stats.users, icon: Users, color: "text-purple-600", bg: "bg-purple-100" },
        ].map((item, i) => (
          <Card key={i} className="bg-white border-slate-200/60 shadow-sm rounded-2xl overflow-hidden hover:shadow-md transition-shadow">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{item.label}</p>
                  <p className={cn("text-xl font-bold mt-1", item.color)}>{item.value}</p>
                </div>
                <div className={cn("p-2.5 rounded-xl", item.bg)}>
                  <item.icon className={cn("h-4 w-4", item.color)} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 租户列表控制栏 */}
      <div className="flex items-center justify-between mt-8">
        <div className="relative w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            placeholder="搜索租户..."
            className="pl-9 h-10 border-slate-200 rounded-xl bg-slate-50/50 focus:bg-white transition-all"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <Button onClick={onNew} className="rounded-xl h-10 px-5 gap-2 shadow-lg shadow-primary/20">
          <Plus className="h-4 w-4" />
          开通租户
        </Button>
      </div>

      {/* 租户表格 */}
      <Card className="border-slate-200/60 shadow-md rounded-2xl overflow-hidden">
        <Table>
          <TableHeader className="bg-slate-50/80">
            <TableRow className="hover:bg-transparent border-slate-100">
              <TableHead className="pl-6 font-bold text-[10px] tracking-widest text-slate-400 uppercase h-12">租户基本信息</TableHead>
              <TableHead className="font-bold text-[10px] tracking-widest text-slate-400 uppercase h-12">订阅与到期</TableHead>
              <TableHead className="font-bold text-[10px] tracking-widest text-slate-400 uppercase h-12">资源配额</TableHead>
              <TableHead className="text-right pr-6 h-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i} className="border-slate-50">
                  <TableCell colSpan={4} className="px-6 py-4">
                    <div className="h-12 bg-slate-50 animate-pulse rounded-xl" />
                  </TableCell>
                </TableRow>
              ))
            ) : filteredTenants.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="h-64 text-center border-none">
                  <div className="flex flex-col items-center gap-2 text-slate-300">
                    <Building2 className="h-10 w-10 opacity-20" />
                    <p className="text-sm font-medium">暂无匹配的租户数据</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredTenants.map((tenant) => (
                <TableRow key={tenant.id} className="group hover:bg-slate-50/50 transition-colors border-slate-100">
                  <TableCell className="pl-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center shrink-0 border border-slate-200 overflow-hidden shadow-sm">
                        {tenant.logo_url ? (
                          <img src={tenant.logo_url} alt={tenant.name} className="w-full h-full object-cover" />
                        ) : (
                          <span className="font-bold text-slate-400 text-xs">{tenant.name.slice(0, 1).toUpperCase()}</span>
                        )}
                      </div>
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900 truncate leading-tight">{tenant.name}</span>
                          <Badge className={cn("text-[9px] px-1.5 h-4 border-none", statusColors[tenant.status] || "bg-slate-100")}>
                            {tenant.status === 'active' ? '活跃' : tenant.status === 'trial' ? '试用' : '禁用'}
                          </Badge>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400 mt-1 uppercase tracking-tight">/{tenant.slug}</span>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1.5">
                      <Badge variant="outline" className={cn("w-fit text-[9px] px-1.5 h-4 font-bold border-none", planColors[tenant.plan] || "bg-slate-100")}>
                        {(tenant.plan || 'starter').toUpperCase()}
                      </Badge>
                      <span className="text-[10px] text-slate-500 font-medium">
                        到期: {new Date(tenant.plan_expires_at).toLocaleDateString()}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-4 text-xs text-slate-500">
                      <div className="flex items-center gap-1.5" title="最大站点">
                        <Globe className="h-3.5 w-3.5 opacity-40" />
                        <span className="font-mono">{tenant.max_sites}</span>
                      </div>
                      <div className="flex items-center gap-1.5" title="最大用户">
                        <Users className="h-3.5 w-3.5 opacity-40" />
                        <span className="font-mono">{tenant.max_users}</span>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-right pr-6">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-slate-400 hover:text-slate-900 border-none">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-[180px] rounded-xl shadow-xl border-slate-100 p-1.5">
                        <DropdownMenuItem onClick={() => onEdit(tenant.id)} className="rounded-lg gap-2 py-2">
                          <Edit2 className="h-4 w-4 text-slate-400" />
                          <span className="text-sm font-medium">编辑资料</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleSwitchTenant(tenant.id)} className="rounded-lg gap-2 py-2">
                          <UserCog className="h-4 w-4 text-slate-400" />
                          <span className="text-sm font-medium">切换此上下文</span>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator className="my-1.5" />
                        <DropdownMenuItem onClick={() => handleDeleteTenant(tenant.id, tenant.name)} className="text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg gap-2 py-2">
                          <Trash2 className="h-4 w-4" />
                          <span className="text-sm font-medium">删除租户</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  )
}

function TenantForm({ tenantId, data, onChange }: {
  tenantId?: number,
  data: any,
  onChange: (data: any) => void
}) {
  const [isInitializing, setIsInitializing] = useState(false)
  const slugManuallyEdited = useRef(false)

  useEffect(() => {
    if (tenantId) {
      setIsInitializing(true)
      api.tenant.get(tenantId)
        .then(t => {
          onChange({
            name: t.name,
            slug: t.slug,
            description: t.description || "",
            logo_url: t.logo_url || "",
            plan: t.plan,
            status: t.status,
            max_sites: t.max_sites,
            max_documents: t.max_documents,
            max_storage_mb: t.max_storage_mb,
            max_users: t.max_users,
            contact_email: t.contact_email || "",
            contact_phone: t.contact_phone || "",
            plan_expires_at: new Date(t.plan_expires_at).toISOString().split('T')[0]
          })
          slugManuallyEdited.current = true
        })
        .finally(() => setIsInitializing(false))
    }
  }, [tenantId])

  // 自动生成 slug
  useEffect(() => {
    if (!tenantId && data.name && !slugManuallyEdited.current) {
      const timer = setTimeout(() => {
        const generated = data.name.toLowerCase()
          .replace(/[^\w\s-]/g, '')
          .replace(/\s+/g, '-')
          .replace(/-+/g, '-')
          .trim()
        onChange({ slug: generated })
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [data.name, tenantId])

  if (isInitializing) return (
    <div className="flex items-center justify-center h-96">
      <Loader2 className="h-8 w-8 animate-spin text-slate-200" />
    </div>
  )

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300 pb-12">
      <div className="grid gap-6">
        {/* 基础信息 */}
        <div className="p-6 bg-gradient-to-br from-slate-50 to-slate-100/30 rounded-3xl border border-slate-200/60 shadow-sm space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-xl text-blue-600">
              <Info className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-bold text-slate-800">基础信息</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">租户显示名称 <span className="text-red-500">*</span></Label>
              <Input
                value={data.name}
                onChange={e => onChange({ name: e.target.value })}
                placeholder="例如：Acme Corporation"
                className="bg-white rounded-xl h-11 border-slate-200"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">唯一标识 (Slug) <span className="text-red-500">*</span></Label>
              <Input
                value={data.slug}
                onChange={e => {
                  slugManuallyEdited.current = true
                  onChange({ slug: e.target.value })
                }}
                disabled={!!tenantId}
                placeholder="例如：acme-corp"
                className="bg-white rounded-xl h-11 border-slate-200 font-mono text-sm disabled:bg-slate-100 disabled:text-slate-400"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">企业描述</Label>
              <Textarea
                value={data.description}
                onChange={e => onChange({ description: e.target.value })}
                placeholder="填写关于该租户的简要介绍..."
                className="bg-white rounded-xl min-h-[110px] resize-none border-slate-200 p-4"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">租户 Logo</Label>
              <ImageUpload
                value={data.logo_url}
                onChange={(url) => onChange({ logo_url: url || "" })}
                compact
              />
            </div>
          </div>
        </div>

        {/* 订阅与状态 */}
        <div className="p-6 bg-gradient-to-br from-purple-50 to-indigo-50/20 rounded-3xl border border-purple-200/40 shadow-sm space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-100 rounded-xl text-purple-600">
              <CreditCard className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-bold text-slate-800">订阅方案与运行状态</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">订阅计划</Label>
              <select
                className="flex h-11 w-full rounded-xl border border-slate-200 bg-white px-3 py-1 text-sm shadow-sm transition-colors focus:ring-2 focus:ring-primary/20 outline-none"
                value={data.plan}
                onChange={(e) => {
                  const plan = e.target.value
                  const config = PLAN_CONFIGS[plan]
                  if (config) {
                    onChange({
                      plan,
                      max_sites: config.max_sites,
                      max_documents: config.max_documents,
                      max_storage_mb: config.max_storage_mb,
                      max_users: config.max_users
                    })
                  } else {
                    onChange({ plan })
                  }
                }}
              >
                <option value="starter">入门版 (Starter)</option>
                <option value="professional">专业版 (Professional)</option>
                <option value="enterprise">企业版 (Enterprise)</option>
                <option value="custom">自定义 (Custom)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">运行状态</Label>
              <select
                className="flex h-11 w-full rounded-xl border border-slate-200 bg-white px-3 py-1 text-sm shadow-sm transition-colors focus:ring-2 focus:ring-primary/20 outline-none"
                value={data.status}
                onChange={(e) => onChange({ status: e.target.value })}
              >
                <option value="active">正常运行 (Active)</option>
                <option value="trial">试用模式 (Trial)</option>
                <option value="disabled">已禁用 (Disabled)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">订阅到期日期</Label>
              <Input
                type="date"
                value={data.plan_expires_at}
                onChange={e => onChange({ plan_expires_at: e.target.value })}
                className="bg-white rounded-xl h-11 border-slate-200"
              />
            </div>
          </div>
        </div>

        {/* 资源配额 */}
        <div className="p-6 bg-gradient-to-br from-emerald-50 to-teal-50/20 rounded-3xl border border-emerald-200/40 shadow-sm space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-100 rounded-xl text-emerald-600">
              <HardDrive className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-bold text-slate-800">资源配额控制</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1 text-xs">最大站点数</Label>
              <Input type="number" value={data.max_sites} onChange={e => onChange({ max_sites: e.target.value })} className="bg-white rounded-xl h-10" />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1 text-xs">最大文档数</Label>
              <Input type="number" value={data.max_documents} onChange={e => onChange({ max_documents: e.target.value })} className="bg-white rounded-xl h-10" />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1 text-xs">最大存储 (MB)</Label>
              <Input type="number" value={data.max_storage_mb} onChange={e => onChange({ max_storage_mb: e.target.value })} className="bg-white rounded-xl h-10" />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1 text-xs">最大用户数</Label>
              <Input type="number" value={data.max_users} onChange={e => onChange({ max_users: e.target.value })} className="bg-white rounded-xl h-10" />
            </div>
          </div>
        </div>

        {/* 联系信息 */}
        <div className="p-6 bg-gradient-to-br from-cyan-50 to-sky-50/20 rounded-3xl border border-cyan-200/40 shadow-sm space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-100 rounded-xl text-cyan-600">
              <Phone className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-bold text-slate-800">商务联系信息</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">联系人邮箱</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  type="email"
                  value={data.contact_email}
                  onChange={e => onChange({ contact_email: e.target.value })}
                  placeholder="contact@example.com"
                  className="bg-white rounded-xl h-11 pl-10"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-700 font-bold ml-1">联系电话</Label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  value={data.contact_phone}
                  onChange={e => onChange({ contact_phone: e.target.value })}
                  placeholder="+86..."
                  className="bg-white rounded-xl h-11 pl-10"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
