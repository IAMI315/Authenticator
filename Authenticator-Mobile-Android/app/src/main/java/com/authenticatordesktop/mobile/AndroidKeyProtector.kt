package com.authenticatordesktop.mobile

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class AndroidKeyProtector(@Suppress("UNUSED_PARAMETER") context: Context) {
    private val alias = "authenticator-mobile-device-key-v1"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setKeySize(256)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    fun protect(value: ByteArray): ByteArray {
        require(value.isNotEmpty()) { "设备密钥数据为空" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(value)
        return byteArrayOf(1, cipher.iv.size.toByte()) + cipher.iv + encrypted
    }

    fun unprotect(value: ByteArray): ByteArray {
        require(value.size > 14 && value[0].toInt() == 1) { "设备密钥格式无效" }
        val nonceLength = value[1].toInt() and 0xff
        require(nonceLength == 12 && value.size > nonceLength + 2) { "设备密钥格式无效" }
        val nonce = value.copyOfRange(2, 2 + nonceLength)
        val encrypted = value.copyOfRange(2 + nonceLength, value.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, nonce))
        return cipher.doFinal(encrypted)
    }
}
