"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { api } from "@/lib/api";
import type { WorkflowDecisionValue } from "@/types";

const decisionSchema = z
  .object({
    decision: z.union([z.literal("APPROVE"), z.literal("REJECT")]),
    reason: z.string().optional(),
  }).refine(
  (data) => {
    if (data.decision === "REJECT") {
      return data.reason !== undefined && data.reason.trim().length > 0;
    }
    return true;
  },
  {
    message: "A reason is required when rejecting.",
    path: ["reason"],
  }
);

type DecisionFormValues = z.infer<typeof decisionSchema>;

interface DecisionFormProps {
  workflowId: string;
  onSuccess?: () => void;
}

export function DecisionForm({ workflowId, onSuccess }: DecisionFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<DecisionFormValues>({
    resolver: zodResolver(decisionSchema),
    defaultValues: {
      decision: undefined,
      reason: "",
    },
  });

  const selected = form.watch("decision");

  async function onSubmit(values: DecisionFormValues) {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const mappedDecision: WorkflowDecisionValue =
        values.decision === "APPROVE" ? "APPROVED" : "REJECTED";
      await api.workflows.decide(workflowId, {
        actor: "HUMAN",
        decision: mappedDecision,
        notes: values.reason || undefined,
      });
      onSuccess?.();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to submit decision");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="decision"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Decision</FormLabel>
              <FormControl>
                <RadioGroup
                  onValueChange={field.onChange}
                  value={field.value}
                  className="flex flex-col space-y-2"
                >
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="APPROVE" id="approve" />
                    <label htmlFor="approve" className="text-sm font-medium cursor-pointer">
                      APPROVE
                    </label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="REJECT" id="reject" />
                    <label htmlFor="reject" className="text-sm font-medium cursor-pointer">
                      REJECT
                    </label>
                  </div>
                </RadioGroup>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {selected && (
          <FormField
            control={form.control}
            name="reason"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Reason {selected === "REJECT" && <span className="text-destructive">*</span>}
                </FormLabel>
                <FormControl>
                  <Textarea
                    placeholder={
                      selected === "REJECT"
                        ? "Reason is required when rejecting."
                        : "Optional notes for approval."
                    }
                    className="min-h-[80px]"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {submitError && (
          <p className="text-sm text-destructive">{submitError}</p>
        )}

        <Button type="submit" disabled={submitting}>
          {submitting ? "Submitting..." : "Submit Decision"}
        </Button>
      </form>
    </Form>
  );
}
