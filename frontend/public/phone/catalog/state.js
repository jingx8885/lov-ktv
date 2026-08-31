import { guardState } from "../../shared/ui/js/guard.js";

/** Mutable state owned by search/library catalog features. */
export const catalogState = guardState(
  {
    previewId: "",
    searchPage: 1,
    searchHits: [],
    libState: { q: "", by: "all", letter: "", page: 1 },
    libTimer: 0,
    libStamp: "",
    libSongs: [],
    libLoading: false,
    libPages: 1,
    libTotal: 0,
    searchLoading: false,
    searchHasMore: false
  },
  "phone.catalog"
);
