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

import { useSettings } from "@/contexts/SettingsContext"
import { useTestConnection } from "@/hooks/useSystemConfig"
import { toast } from "sonner"
import { MODEL_TYPES, initialConfigs } from "@/types/settings"

type RuntimeModelType = typeof MODEL_TYPES[number]

export function useModelConfigLogic(type: RuntimeModelType, onSuccess?: () => void) {
  const { configs, handleUpdate, handleSave, scope, platformDefaults } = useSettings()
  const testConnection = useTestConnection(scope)

  const config = configs[type] || initialConfigs[type]
  const hasPlatformResource = !!(platformDefaults && platformDefaults[type] && platformDefaults[type].api_key)
  const mode = config.mode || "custom"

  const handleModeChange = (newMode: "custom" | "platform") => {
    handleUpdate(type, "mode", newMode)
  }

  const handleTest = () => {
    testConnection.mutate(
      { modelType: type, config },
      {
        onSuccess: (data: unknown) => {
          toast.success("连接测试成功")
          if (
            data &&
            typeof data === 'object' &&
            'dimension' in data &&
            typeof (data as { dimension?: unknown }).dimension === 'number'
          ) {
            handleUpdate(type, "dimension", (data as { dimension: number }).dimension)
          }
        },
        onError: (err) => {
          toast.error(err.message || "连接测试失败")
        }
      }
    )
  }

  const handleSaveWithCheck = async () => {
    if (mode === "platform") {
      try {
        await handleSave(type)
        onSuccess?.()
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : "保存失败")
      }
      return
    }

    try {
      const data = await testConnection.mutateAsync({ modelType: type, config })
      // 与 handleTest 一致：如果测试返回了 dimension（如 embedding 模型），更新 UI 状态
      // 同时通过 overrides 直接传入 handleSave，避免 setState 异步时序问题
      const overrides: Record<string, string | number | boolean | Record<string, unknown>> = {}
      if (
        data &&
        typeof data === 'object' &&
        'dimension' in data &&
        typeof (data as { dimension?: unknown }).dimension === 'number'
      ) {
        const dim = (data as { dimension: number }).dimension
        handleUpdate(type, "dimension", dim)
        overrides.dimension = dim
      }
      await handleSave(type, overrides)
      onSuccess?.()
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "连接测试发生错误，无法保存")
    }
  }

  return {
    config,
    baseConfig: {
      model: config.model,
      api_key: config.api_key,
      base_url: config.base_url,
      dimension: config.dimension,
      extra_body: config.extra_body
    },
    mode,
    hasPlatformResource,
    isTesting: testConnection.isPending,
    handleModeChange,
    handleTest,
    handleSave: handleSaveWithCheck,
    handleUpdate
  }
}
