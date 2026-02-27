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

/**
 * 模型配置字段组件 - 手动模式下的详细配置表单
 */

"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Save, ShieldCheck, BrainCircuit } from "lucide-react"
import type { ModelConfig } from "@/lib/api-client"

interface ModelConfigFieldsProps {
  type: "chat" | "embedding" | "rerank" | "vl"
  config: ModelConfig
  onUpdate: (field: string, value: any) => void
  onSave: () => void
}

const MODEL_TYPE_LABELS = {
  chat: "对话",
  embedding: "向量",
  rerank: "重排",
  vl: "视觉"
}

export function ModelConfigFields({ type, config, onUpdate, onSave }: ModelConfigFieldsProps) {
  const isThinkingEnabled = config.extra_body?.chat_template_kwargs?.enable_thinking ?? false;

  const handleThinkingChange = (checked: boolean) => {
    const currentExtraBody = config.extra_body || {};
    const currentKwargs = currentExtraBody.chat_template_kwargs || {};
    onUpdate("extra_body", {
      ...currentExtraBody,
      chat_template_kwargs: {
        ...currentKwargs,
        enable_thinking: checked
      }
    });
  };

  return (
    <div className="space-y-6 pt-4">
      {/* ... (rest of the component) */}
      {/* Search for line 129 and fix it below */}
      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-700">模型提供商</label>
          <Select
            value={config.provider}
            onValueChange={(val) => onUpdate("provider", val)}
          >
            <SelectTrigger className="w-full bg-white">
              <SelectValue placeholder="选择提供商" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="deepseek">DeepSeek (深度求索)</SelectItem>
              <SelectItem value="siliconflow">SiliconFlow (硅基流动)</SelectItem>
              <SelectItem value="moonshot">月之暗面 (Moonshot)</SelectItem>
              <SelectItem value="bailian">阿里云百炼 (Qwen)</SelectItem>
              <SelectItem value="volcengine">火山引擎 (豆包)</SelectItem>
              <SelectItem value="openai">OpenAI / 兼容代理</SelectItem>
              <SelectItem value="local">Local (Ollama / vLLM)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-semibold text-slate-700">模型名称</label>
          <Input
            value={config.model}
            onChange={(e) => onUpdate("model", e.target.value)}
            placeholder="例如: gpt-4, claude-3-opus..."
            autoComplete="new-password"
            name="model_name_disable_autofill"
            className="bg-white"
          />
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-semibold text-slate-700">API Key</label>
        <Input
          type="password"
          value={config.api_key}
          onChange={(e) => onUpdate("api_key", e.target.value)}
          placeholder="sk-..."
          autoComplete="new-password"
          name="model_api_key_disable_autofill"
          className="bg-white font-mono"
        />
      </div>

      <div className="space-y-2">
        <label className="text-sm font-semibold text-slate-700">API Base URL</label>
        <Input
          value={config.base_url}
          onChange={(e) => onUpdate("base_url", e.target.value)}
          placeholder="https://api.openai.com/v1"
          className="bg-white font-mono"
        />
      </div>

      {type === "chat" && (
        <div className="bg-slate-50/50 p-4 rounded-2xl border border-slate-100 flex items-center justify-between transition-all hover:bg-slate-50">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-violet-100 flex items-center justify-center text-violet-600 shadow-sm">
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

      <div className="pt-6 border-t border-slate-100 flex items-center justify-between">
        <div className="bg-slate-50 px-4 py-2 rounded-xl flex items-center gap-3">
          <ShieldCheck className="h-4 w-4 text-emerald-500" />
          <p className="text-[10px] text-slate-500">
            API Key 已加密存储。请确保该供应商余额充足。
          </p>
        </div>
        <Button
          onClick={onSave}
          className="flex items-center gap-2 h-10 px-6 rounded-xl shadow-md"
        >
          <Save className="h-4 w-4" />
          保存{MODEL_TYPE_LABELS[type]}配置
        </Button>
      </div>
    </div>
  )
}

