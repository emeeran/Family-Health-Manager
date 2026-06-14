/**
 * Natural-language extraction hook — mirrors useFileExtraction's interface but
 * routes a free-text box through parseNaturalLanguage + the SAME mergeExtractedFields
 * logic, so "describe it in words" populates an editable form.
 */
import { useState, useMemo, useCallback } from "react";
import type { UseFormReturn } from "react-hook-form";
import { parseNaturalLanguage, type NLParseResponse } from "@/lib/api/records";
import { getConfig, getTables } from "@/lib/record-type-configs";
import { mergeExtractedFields, extractedFromNL, typeSpecificFieldsFromNL } from "./merge-extracted";
import type { FormValues } from "./record-form-utils";
import type { RecordType } from "@/lib/types/enums";
import type { ProviderResponse } from "@/lib/types/provider";

interface UseNLExtractionArgs {
  recordType: RecordType | undefined;
  providerList: ProviderResponse[];
  form: Pick<UseFormReturn<FormValues>, "setValue" | "getValues">;
  setCustomValues: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setTableData: React.Dispatch<React.SetStateAction<Record<string, Record<string, string>[]>>>;
  setExtractedFields: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export function useNLExtraction({
  recordType,
  providerList,
  form,
  setCustomValues,
  setTableData,
  setExtractedFields,
}: UseNLExtractionArgs) {
  const [nlText, setNlText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [nlError, setNlError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<NLParseResponse | null>(null);

  const tables = useMemo(() => (recordType ? getTables(getConfig(recordType)) : []), [recordType]);

  const parseText = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setNlText(text);
      setParsing(true);
      setNlError(null);
      try {
        const result = await parseNaturalLanguage(trimmed);
        setParsed(result);
        const { populated } = mergeExtractedFields(
          { providerList, form, setCustomValues, setTableData, setExtractedFields, tables },
          extractedFromNL(result),
          typeSpecificFieldsFromNL(result)
        );
        if (populated.size === 0) {
          setNlError(
            "Couldn't extract any fields from that text — try rephrasing with more detail."
          );
        }
      } catch (e) {
        setParsed(null);
        setNlError(e instanceof Error ? e.message : "Failed to parse text");
      } finally {
        setParsing(false);
      }
    },
    [providerList, form, setCustomValues, setTableData, setExtractedFields, tables]
  );

  const handleParse = useCallback(() => parseText(nlText), [parseText, nlText]);

  const clearNL = useCallback(() => {
    setNlText("");
    setParsed(null);
    setNlError(null);
  }, []);

  return {
    nlText,
    setNlText,
    parsing,
    nlError,
    setNlError,
    parsed,
    handleParse,
    parseText,
    clearNL,
  };
}
