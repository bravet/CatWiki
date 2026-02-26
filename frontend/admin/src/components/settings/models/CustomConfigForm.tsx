// Copyright 2026 CatWiki Authors
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

import { Input } from "@/components/ui/input"
import { ShieldCheck, BrainCircuit } from "lucide-react"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"

interface CustomConfigFormProps {
  type: "chat" | "embedding" | "rerank" | "vl"
  config: {
    model: string
    apiKey: string
    baseUrl: string
    dimension?: number | null
    extra_body?: Record<string, any> | null
  }
  onUpdate: (type: "chat" | "embedding" | "rerank" | "vl", field: string, value: any) => void
}

export function CustomConfigForm({ type, config, onUpdate }: CustomConfigFormProps) {
  const isThinkingEnabled = config.extra_body?.chat_template_kwargs?.enable_thinking ?? false;

  const handleThinkingChange = (checked: boolean) => {
    const currentExtraBody = config.extra_body || {};
    const currentKwargs = currentExtraBody.chat_template_kwargs || {};
    onUpdate(type, "extra_body", {
      ...currentExtraBody,
      chat_template_kwargs: {
        ...currentKwargs,
        enable_thinking: checked
      }
    });
  };

  return (
    <>
      {type === "embedding" && (
        <div className="bg-amber-50 border border-amber-200 rounded-md p-4 flex gap-3 text-amber-900 text-sm">
          <div className="shrink-0 mt-0.5">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5 text-amber-600"
            >
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="font-medium text-amber-800">更改需谨慎</p>
            <p>修改向量模型配置可能导致现有的向量知识库无法检索！</p>
            <p>一旦修改，建议在&quot;文档管理&quot;中对所有文档执行&quot;重新向量化&quot;操作，否则旧数据的向量将与新模型不兼容。</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-700">协议类型</label>
          <div className="flex items-center h-10 px-3 rounded-md border border-slate-200 bg-slate-50 text-slate-500 text-sm">
            OpenAI API 兼容协议
          </div>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-700">模型名称</label>
          <Input
            value={config.model}
            onChange={(e) => onUpdate(type, "model", e.target.value)}
            placeholder="例如: gpt-4, claude-3-opus..."
            className="bg-white"
            autoComplete="new-password"
            name="custom_model_disable_autofill"
          />
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-semibold text-slate-700">API Key</label>
        <Input
          type="password"
          value={config.apiKey}
          onChange={(e) => onUpdate(type, "apiKey", e.target.value)}
          placeholder="sk-..."
          className="bg-white font-mono"
          autoComplete="new-password"
          name="custom_apiKey_disable_autofill"
        />
      </div>

      <div className="space-y-2">
        <label className="text-sm font-semibold text-slate-700">API Base URL</label>
        <Input
          value={config.baseUrl}
          onChange={(e) => onUpdate(type, "baseUrl", e.target.value)}
          placeholder="https://api.openai.com/v1"
          className="bg-white font-mono"
        />
      </div>

      {type === "embedding" && (
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-700">向量维度 (自动获取)</label>
          <div className="flex gap-2">
            <Input
              type="number"
              value={config.dimension || ""}
              disabled={true}
              placeholder="等待自动探测..."
              className="bg-slate-50 font-mono text-slate-500"
            />
          </div>
          <p className="text-xs text-slate-500">
            该值将在保存配置时自动从模型提供商探测。
          </p>
        </div>
      )}
      {type === "chat" && (
        <div className="bg-slate-50/50 p-4 rounded-xl border border-slate-100 flex items-center justify-between transition-all hover:bg-slate-50">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-violet-100 flex items-center justify-center text-violet-600 shadow-sm">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div className="space-y-0.5">
              <Label htmlFor="thinking-mode" className="text-sm font-bold text-slate-800 cursor-pointer">
                是否开启思考
              </Label>
              <p className="text-[11px] text-slate-500">调用模型时是否请求思考/推理过程 (extra_body)</p>
            </div>
          </div>
          <Switch
            id="thinking-mode"
            checked={isThinkingEnabled}
            onCheckedChange={handleThinkingChange}
            className="data-[state=checked]:bg-violet-600"
          />
        </div>
      )}
    </>
  )
}
