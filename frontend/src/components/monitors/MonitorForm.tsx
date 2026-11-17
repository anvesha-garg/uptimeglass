import { useId, useState } from "react";
import type { FormEvent } from "react";

import { ApiError } from "../../api/client";
import type { Monitor } from "../../api/monitors";
import { useSaveMonitor } from "../../hooks/useMonitors";
import { errorMessage } from "../../lib/errors";
import { DEFAULT_VALUES, validateForm, valuesFromMonitor } from "../../lib/monitorForm";
import type { FormErrors, FormValues } from "../../lib/monitorForm";
import { GlassButton } from "../glass/GlassButton";
import { GlassInput } from "../glass/GlassInput";
import { GlassModal } from "../glass/GlassModal";
import { useToast } from "../glass/toast-context";

interface MonitorFormProps {
  /** The monitor to edit, or null to create a new one. Mount this only while it is open. */
  monitor: Monitor | null;
  onClose: () => void;
}

export function MonitorForm({ monitor, onClose }: MonitorFormProps) {
  const [values, setValues] = useState<FormValues>(() =>
    monitor ? valuesFromMonitor(monitor) : DEFAULT_VALUES,
  );
  const [errors, setErrors] = useState<FormErrors>({});
  const save = useSaveMonitor(monitor?.id ?? null);
  const { show } = useToast();
  const methodId = useId();

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const result = validateForm(values);
    setErrors(result.errors);
    if (!result.input) return;

    save.mutate(result.input, {
      onSuccess: () => {
        show(monitor ? "Monitor updated." : "Monitor created.", "success");
        onClose();
      },
      onError: (error) => {
        // A refused address belongs next to the URL field. Other errors show above the buttons.
        if (error instanceof ApiError && error.code === "invalid_url") {
          setErrors({ url: error.message });
        }
      },
    });
  }

  const isUrlError = save.error instanceof ApiError && save.error.code === "invalid_url";
  const formError = save.error && !isUrlError ? errorMessage(save.error) : null;

  return (
    <GlassModal open onClose={onClose} title={monitor ? "Edit monitor" : "Add monitor"}>
      <form className="monitor-form" onSubmit={onSubmit} noValidate>
        <GlassInput
          label="Name"
          value={values.name}
          onChange={(event) => set("name", event.target.value)}
          error={errors.name}
          placeholder="My website"
        />
        <GlassInput
          label="URL"
          type="text"
          inputMode="url"
          autoComplete="off"
          value={values.url}
          onChange={(event) => set("url", event.target.value)}
          error={errors.url}
          placeholder="https://example.com"
        />
        <div className="field">
          <label htmlFor={methodId} className="field__label">
            Method
          </label>
          <select
            id={methodId}
            className="field__input"
            value={values.method}
            onChange={(event) => set("method", event.target.value as "GET" | "HEAD")}
          >
            <option value="GET">GET</option>
            <option value="HEAD">HEAD (no keyword check)</option>
          </select>
        </div>
        <div className="monitor-form__row">
          <GlassInput
            label="Check every (seconds)"
            type="number"
            inputMode="numeric"
            min={60}
            value={values.interval}
            onChange={(event) => set("interval", event.target.value)}
            error={errors.interval}
          />
          <GlassInput
            label="Timeout (seconds)"
            type="number"
            inputMode="numeric"
            min={1}
            value={values.timeout}
            onChange={(event) => set("timeout", event.target.value)}
            error={errors.timeout}
          />
          <GlassInput
            label="Expected status"
            type="number"
            inputMode="numeric"
            value={values.expectedStatus}
            onChange={(event) => set("expectedStatus", event.target.value)}
            error={errors.expectedStatus}
          />
        </div>
        <GlassInput
          label="Keyword (optional)"
          hint="The page must contain this text. Needs the GET method."
          value={values.keyword}
          onChange={(event) => set("keyword", event.target.value)}
          error={errors.keyword}
        />
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <div className="monitor-form__actions">
          <GlassButton type="submit" loading={save.isPending}>
            {monitor ? "Save changes" : "Create monitor"}
          </GlassButton>
          <GlassButton variant="secondary" onClick={onClose}>
            Cancel
          </GlassButton>
        </div>
      </form>
    </GlassModal>
  );
}
