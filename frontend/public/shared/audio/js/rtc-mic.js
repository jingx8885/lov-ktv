(function (global) {
  const ICE = [{ urls: "stun:stun.l.google.com:19302" }];

  function tt(key, fallback) {
    return (global.LovI18n && global.LovI18n.t(key)) || fallback;
  }

  function newPeerId() {
    return "p" + Math.random().toString(36).slice(2, 10);
  }

  function create(opts) {
    const peerId = (opts && opts.peerId) || newPeerId();
    const role = (opts && opts.role) || "phone";
    let ws = null;
    let pc = null;
    let localStream = null;
    let handlers = {};
    let code = "";
    let closed = false;
    let pendingIce = [];
    let outbox = [];

    function send(msg) {
      if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify(msg));
        return;
      }
      outbox.push(msg);
    }

    function flushOutbox() {
      const queued = outbox.splice(0);
      queued.forEach((msg) => send(msg));
    }

    function emitState(state) {
      if (handlers.onState) handlers.onState(state);
    }

    function connect(roomCode, next) {
      code = String(roomCode || "").toUpperCase();
      handlers = next || {};
      closed = false;
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const url = proto + "//" + location.host + "/ws/rooms/" + encodeURIComponent(code);
      if (ws) {
        try {
          ws.onclose = null;
          ws.close();
        } catch (err) {}
      }
      ws = new WebSocket(url);
      ws.onopen = () => {
        send({ action: "hello", role, peer: peerId });
        flushOutbox();
        if (handlers.onOpen) handlers.onOpen();
      };
      ws.onmessage = (event) => {
        let msg = null;
        try {
          msg = JSON.parse(event.data);
        } catch (err) {
          return;
        }
        if (!msg) return;
        if (msg.type === "snapshot" && handlers.onSnapshot) handlers.onSnapshot(msg.room);
        if (msg.type === "peer" && handlers.onPeer) handlers.onPeer(msg);
        if (msg.type === "rtc" && handlers.onRtc) handlers.onRtc(msg);
        if (msg.type === "error" && handlers.onError) handlers.onError(msg);
      };
      ws.onclose = () => {
        if (closed) return;
        setTimeout(() => {
          if (!closed && code) connect(code, handlers);
        }, 1200);
      };
    }

    function disconnect() {
      closed = true;
      outbox = [];
      if (ws) {
        try {
          ws.close();
        } catch (err) {}
        ws = null;
      }
    }

    function waitOpen() {
      if (ws && ws.readyState === 1) return Promise.resolve();
      return new Promise((resolve, reject) => {
        const started = Date.now();
        const tick = setInterval(() => {
          if (ws && ws.readyState === 1) {
            clearInterval(tick);
            resolve();
          } else if (Date.now() - started > 5000) {
            clearInterval(tick);
            reject(new Error(tt("mic.wsWait", "房间连接还没好，再点一次开麦")));
          }
        }, 80);
      });
    }

    async function resetPc() {
      pendingIce = [];
      if (pc) {
        try {
          pc.ontrack = null;
          pc.onicecandidate = null;
          pc.onconnectionstatechange = null;
          pc.oniceconnectionstatechange = null;
          pc.close();
        } catch (err) {}
        pc = null;
      }
    }

    function flushIce() {
      if (!pc || !pc.remoteDescription) return;
      const batch = pendingIce.splice(0);
      batch.forEach((candidate) => {
        pc.addIceCandidate(candidate).catch(() => {});
      });
    }

    function liveLabel() {
      if (!pc) return "closed";
      const ice = pc.iceConnectionState;
      const conn = pc.connectionState;
      if (conn === "connected" || ice === "connected" || ice === "completed") return "connected";
      if (conn === "failed" || ice === "failed") return "failed";
      if (conn === "disconnected" || ice === "disconnected") return "disconnected";
      return conn || ice || "connecting";
    }

    function bindIce() {
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          send({ action: "rtc", kind: "ice", from: peerId, candidate: event.candidate });
        }
      };
      pc.onconnectionstatechange = () => emitState(liveLabel());
      pc.oniceconnectionstatechange = () => emitState(liveLabel());
    }

    async function addIce(msg) {
      if (!msg || !msg.candidate) return;
      if (!pc || !pc.remoteDescription) {
        pendingIce.push(msg.candidate);
        return;
      }
      try {
        await pc.addIceCandidate(msg.candidate);
      } catch (err) {}
    }

    async function makeOffer() {
      if (!localStream) return;
      await resetPc();
      pc = new RTCPeerConnection({ iceServers: ICE });
      localStream.getTracks().forEach((track) => pc.addTrack(track, localStream));
      bindIce();
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ action: "rtc", kind: "offer", from: peerId, sdp: pc.localDescription });
    }

    async function startMic() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(tt("mic.noDevice", "这台手机不能开麦"));
      }
      await waitOpen();
      localStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1
        },
        video: false
      });
      await makeOffer();
      send({ action: "mic", on: true, from: peerId });
      return localStream;
    }

    async function handleAnswer(msg) {
      if (!pc || !msg || !msg.sdp) return;
      if (pc.signalingState === "stable") return;
      await pc.setRemoteDescription(msg.sdp);
      flushIce();
    }

    async function handleOffer(msg) {
      if (!msg || !msg.sdp) return;
      const kept = pendingIce.splice(0);
      await resetPc();
      pendingIce = kept;
      pc = new RTCPeerConnection({ iceServers: ICE });
      bindIce();
      pc.ontrack = (event) => {
        const stream =
          event.streams && event.streams[0] ? event.streams[0] : new MediaStream(event.track ? [event.track] : []);
        if (handlers.onStream) handlers.onStream(stream);
      };
      await pc.setRemoteDescription(msg.sdp);
      flushIce();
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      send({ action: "rtc", kind: "answer", from: peerId, sdp: pc.localDescription });
    }

    async function stopMic() {
      if (localStream) {
        localStream.getTracks().forEach((track) => track.stop());
        localStream = null;
      }
      send({ action: "rtc", kind: "hangup", from: peerId });
      send({ action: "mic", on: false, from: peerId });
      await resetPc();
    }

    function isLive() {
      return !!(localStream && localStream.getTracks().some((track) => track.readyState === "live"));
    }

    return {
      peerId,
      connect,
      disconnect,
      send,
      startMic,
      stopMic,
      makeOffer,
      handleAnswer,
      handleOffer,
      addIce,
      resetPc,
      isLive
    };
  }

  function micErrorText(err) {
    const name = err && err.name;
    const raw = String((err && err.message) || err || "");
    if (name === "NotAllowedError" || /permission|denied|notallowed/i.test(raw)) {
      return tt("mic.denied", "没拿到麦克风权限。系统设置里打开，或用 Safari 打开本页。");
    }
    if (name === "NotFoundError") return tt("mic.notFound", "没找到麦克风");
    if (name === "NotReadableError") return tt("mic.busy", "麦克风正被别的 App 占用");
    if (name === "SecurityError" || /getUserMedia|secure|https/i.test(raw)) {
      return tt("mic.insecure", "开麦需要安全连接。用 https 打开，或把这页加到主屏幕后再试。");
    }
    return raw || tt("mic.fail", "开麦失败");
  }

  global.LovMic = { create, micErrorText };
})(window);
