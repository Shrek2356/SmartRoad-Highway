// Only the newest request may update a page; disposal invalidates all work.
export function createRequestGate() {
  let revision = 0, disposed = false
  return {
    begin: () => ++revision,
    current: token => !disposed && token === revision,
    dispose: () => { disposed = true; revision++ },
  }
}
