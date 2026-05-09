import type { AggregatedQuestion, AuditFormResult, FormCatalogEntry, ReviewRecord } from "@/lib/types";

const baseQuestions = [
  {
    id: "Q1",
    text: "Was the file documentation sufficient to support the estimate decision?",
    answer: "Yes" as const,
    sub_questions: [],
    missing_info: null,
    help_text: "Review notes, photos, estimate line items, and supporting attachments.",
  },
  {
    id: "Q2",
    text: "Were all applicable repair opportunities addressed?",
    answer: "No" as const,
    sub_questions: [
      {
        id: "Q2.1",
        text: "An applicable repair item appears missing or under-scoped.",
        reasoning: "The estimate omits a drywall repair that is visible in the inspection photos.",
        citations: "Photo set 14-16; adjuster note 03/21.",
        answer: true,
        help_text: "Cite the evidence supporting the opportunity.",
      },
      {
        id: "Q2.2",
        text: "The pricing or quantity appears unsupported by the file evidence.",
        reasoning: "",
        citations: "",
        answer: false,
        help_text: null,
      },
    ],
    missing_info: null,
    help_text: null,
  },
  {
    id: "Q3",
    text: "Is there enough evidence to determine the applicable peril?",
    answer: "Insufficient information" as const,
    sub_questions: [],
    missing_info: "The file does not include the final field inspection narrative.",
    help_text: null,
  },
];

export const reviews: ReviewRecord[] = [
  {
    id: "rev-1001",
    feedback: "up",
    comments: "Agent found the main issue, but the peril note needed tightening.",
    original: {
      id: "rev-1001",
      form_id: "tfr_default",
      form_version: "v0.1",
      title: "Claim 24019 Interior Review",
      peril: { peril: "Interior", notes: "Water damage reported near kitchen ceiling." },
      questions: baseQuestions,
      overall_outcome: "Does Not Meet",
      outcome_justification: "A repair opportunity was identified and required evidence is incomplete.",
      created_at: "2026-05-07T15:21:00Z",
      updated_at: "2026-05-08T11:02:00Z",
    },
    userVersion: {
      id: "rev-1001",
      form_id: "tfr_default",
      form_version: "v0.1",
      title: "Claim 24019 Interior Review",
      peril: { peril: "Interior", notes: "Water damage reported near the kitchen and hallway ceiling." },
      questions: baseQuestions.map((question) =>
        question.id === "Q3"
          ? {
              ...question,
              missing_info: "The field inspection narrative is missing from the uploaded packet.",
            }
          : question,
      ),
      overall_outcome: "Does Not Meet",
      outcome_justification: "A repair opportunity was identified; user clarified the missing evidence.",
      created_at: "2026-05-07T15:21:00Z",
      updated_at: "2026-05-08T14:36:00Z",
    },
  },
  {
    id: "rev-1002",
    feedback: null,
    comments: "",
    original: {
      id: "rev-1002",
      form_id: "tfr_default",
      form_version: "v0.1",
      title: "Claim 24022 Exterior Review",
      peril: { peril: "Exterior", notes: "Wind/hail review with roof photo packet." },
      questions: baseQuestions.map((question) =>
        question.id === "Q2" ? { ...question, answer: "Yes" as const, sub_questions: [] } : question,
      ),
      overall_outcome: "Meets",
      outcome_justification: "The file supports the estimate and no repair opportunity was identified.",
      created_at: "2026-05-08T10:08:00Z",
      updated_at: "2026-05-08T10:22:00Z",
    },
    userVersion: {
      id: "rev-1002",
      form_id: "tfr_default",
      form_version: "v0.1",
      title: "Claim 24022 Exterior Review",
      peril: { peril: "Exterior", notes: "Wind/hail review with roof photo packet." },
      questions: baseQuestions.map((question) =>
        question.id === "Q2" ? { ...question, answer: "Yes" as const, sub_questions: [] } : question,
      ),
      overall_outcome: "Meets",
      outcome_justification: "The file supports the estimate and no repair opportunity was identified.",
      created_at: "2026-05-08T10:08:00Z",
      updated_at: "2026-05-08T10:22:00Z",
    },
  },
  {
    id: "rev-1003",
    feedback: "down",
    comments: "Missed a clear sub-question driver.",
    original: {
      id: "rev-1003",
      form_id: "tfr_default",
      form_version: "v0.1",
      title: "Claim 24031 Interior Review",
      peril: { peril: "Interior", notes: null },
      questions: baseQuestions.map((question) =>
        question.id === "Q2" ? { ...question, answer: "Yes" as const, sub_questions: [] } : question,
      ),
      overall_outcome: "Meets",
      outcome_justification: "The uploaded materials appear to support the estimate.",
      created_at: "2026-05-08T16:44:00Z",
      updated_at: "2026-05-08T16:50:00Z",
    },
    userVersion: {
      id: "rev-1003",
      form_id: "tfr_default",
      form_version: "v0.1",
      title: "Claim 24031 Interior Review",
      peril: { peril: "Interior", notes: "Interior water loss." },
      questions: baseQuestions,
      overall_outcome: "Does Not Meet",
      outcome_justification: "User identified an omitted repair item in the estimate.",
      created_at: "2026-05-08T16:44:00Z",
      updated_at: "2026-05-08T17:19:00Z",
    },
  },
];

export const savedForms: AuditFormResult[] = reviews.map((review) => review.userVersion);

export const formCatalog: FormCatalogEntry[] = [
  {
    id: "tfr_default",
    version: "v0.1",
    title: "Default TFR Questionnaire",
    description: "Starter canonical form for question, sub-question, peril, and outcome workflows.",
    questionCount: 3,
    status: "active",
    lastUpdated: "2026-05-09",
  },
  {
    id: "interior_water",
    version: "draft",
    title: "Interior Water Loss",
    description: "Draft variant for interior water file reviews and repair-scope checks.",
    questionCount: 8,
    status: "draft",
    lastUpdated: "2026-05-09",
  },
  {
    id: "exterior_hail",
    version: "draft",
    title: "Exterior Hail Review",
    description: "Draft variant for exterior peril determination and roof/siding evidence review.",
    questionCount: 10,
    status: "draft",
    lastUpdated: "2026-05-09",
  },
];

export const aggregatedQuestions: AggregatedQuestion[] = [
  {
    id: "Q1",
    text: "Was the file documentation sufficient to support the estimate decision?",
    yesCount: 3,
    noCount: 0,
    insufficientCount: 0,
    totalCount: 3,
    editCount: 0,
  },
  {
    id: "Q2",
    text: "Were all applicable repair opportunities addressed?",
    yesCount: 1,
    noCount: 2,
    insufficientCount: 0,
    totalCount: 3,
    editCount: 1,
  },
  {
    id: "Q3",
    text: "Is there enough evidence to determine the applicable peril?",
    yesCount: 0,
    noCount: 0,
    insufficientCount: 3,
    totalCount: 3,
    editCount: 1,
  },
];

