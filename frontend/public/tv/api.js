/** @type {TvApi} */
export const api = /** @type {TvApi} */ ({});

/** @param {TvApi} bag */
export function installApi(bag) {
  Object.assign(api, bag);
}
