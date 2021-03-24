# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

"""
The `edx-django-oauth2-provider` has been deprecated in favor of `django-oauth-toolkit`.
Its tables however persist in database. They have foreign key dependancy with `auth_user.id`. Django does
not resolves this constratint and we are unable to remove users.

This migration changes the on_delete behaviour of foreign keys in these tables from default which is
`NO ACTION` and set it to `CASCADE`.
"""


class Migration(migrations.Migration):

    dependencies = [
        ('database_fixups', '0002_remove_foreign_keys_from_progress_extensions'),
    ]

    operations = [
        migrations.RunSQL(
            """
            -- Drop a procedure if it already exists - safety check.
            DROP PROCEDURE IF EXISTS alter_foreign_key_from_oauth2_table;

            -- We are altering constraints from 3 tables, so we create a temporary procedure to avoid code repetition.
            CREATE PROCEDURE alter_foreign_key_from_oauth2_table(given_table VARCHAR(64))
            BEGIN
                -- There are two foregin keys, one that refers to auth_user, one that refers to oath2_client
                SET @auth_foreign_key = (
                    SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE REFERENCED_TABLE_SCHEMA='edxapp'
                        AND REFERENCED_TABLE_NAME='auth_user'
                        AND TABLE_NAME=given_table
                );
                SET @client_foreign_key = (
                    SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE REFERENCED_TABLE_SCHEMA='edxapp'
                        AND REFERENCED_TABLE_NAME='oauth2_client'
                        AND TABLE_NAME=given_table
                );

                IF @auth_foreign_key IS NOT NULL THEN
                    -- DROP the existing foreign key and create a new one with CASCADE on delete behaviour.
                    SET @statement1 = CONCAT('ALTER TABLE ', given_table, ' DROP FOREIGN KEY ', @auth_foreign_key);
                    PREPARE stmt FROM @statement1;
                    EXECUTE stmt;
                    SET @statement2 = CONCAT(
                        'ALTER TABLE ', given_table, ' ADD CONSTRAINT ', @auth_foreign_key,
                        ' FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`) ON DELETE CASCADE'
                    );
                    PREPARE stmt FROM @statement2;
                    EXECUTE stmt;
                    DEALLOCATE PREPARE stmt;
                END IF;

                IF @client_foreign_key IS NOT NULL THEN
                    -- DROP the existing foreign key and create a new one with CASCADE on delete behaviour.
                    SET @statement1 = CONCAT('ALTER TABLE ', given_table, ' DROP FOREIGN KEY ', @client_foreign_key);
                    PREPARE stmt FROM @statement1;
                    EXECUTE stmt;
                    SET @statement2 = CONCAT(
                        'ALTER TABLE ', given_table, ' ADD CONSTRAINT ', @client_foreign_key,
                        ' FOREIGN KEY (`client_id`) REFERENCES `oauth2_client` (`id`) ON DELETE CASCADE'
                    );
                    PREPARE stmt FROM @statement2;
                    EXECUTE stmt;
                    DEALLOCATE PREPARE stmt;
                END IF;
            END;

            -- Call temporary procedure on relevant tables.
            CALL alter_foreign_key_from_oauth2_table('oauth2_client');
            CALL alter_foreign_key_from_oauth2_table('oauth2_grant');
            CALL alter_foreign_key_from_oauth2_table('oauth2_accesstoken');

            -- Clean up.
            DROP PROCEDURE IF EXISTS alter_foreign_key_from_oauth2_table;
        """,
            reverse_sql="""
            -- Drop a procedure if it already exists - safety check.
            DROP PROCEDURE IF EXISTS drop_oauth2_foreign_keys;

            -- We are dropping constraints from 3 tables, so we create a temporary procedure to avoid code repetition.
            CREATE PROCEDURE drop_oauth2_foreign_keys(given_table VARCHAR(64))
            BEGIN
                -- There are two foregin keys, one that refers to auth_user, one that refers to oath2_client
                SET @auth_foreign_key = (
                    SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE REFERENCED_TABLE_SCHEMA='edxapp'
                        AND REFERENCED_TABLE_NAME='auth_user'
                        AND TABLE_NAME=given_table
                );
                SET @client_foreign_key = (
                    SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE REFERENCED_TABLE_SCHEMA='edxapp'
                        AND REFERENCED_TABLE_NAME='oauth2_client'
                        AND TABLE_NAME=given_table
                );

                IF @auth_foreign_key IS NOT NULL THEN
                    -- DROP the existing foreign key and create a new one with CASCADE on delete.
                    SET @statement = CONCAT('ALTER TABLE ', given_table, ' DROP FOREIGN KEY ', @auth_foreign_key);
                    PREPARE stmt FROM @statement;
                    EXECUTE stmt;
                    DEALLOCATE PREPARE stmt;
                END IF;

                IF @client_foreign_key IS NOT NULL THEN
                    -- DROP the existing foreign key and create a new one with CASCADE on delete.
                    SET @statement = CONCAT('ALTER TABLE ', given_table, ' DROP FOREIGN KEY ', @client_foreign_key);
                    PREPARE stmt FROM @statement;
                    EXECUTE stmt;
                    DEALLOCATE PREPARE stmt;
                END IF;
            END;

            -- Call temporary procedure on relevant tables.
            CALL drop_oauth2_foreign_keys('oauth2_client');
            CALL drop_oauth2_foreign_keys('oauth2_grant');
            CALL drop_oauth2_foreign_keys('oauth2_accesstoken');

            -- Clean up.
            DROP PROCEDURE IF EXISTS drop_oauth2_foreign_keys;

            -- Add original foreign key constraints again
            ALTER TABLE `oauth2_client` ADD FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);
            ALTER TABLE `oauth2_grant` ADD FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);
            ALTER TABLE `oauth2_accesstoken` ADD FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

            ALTER TABLE `oauth2_grant` ADD FOREIGN KEY (`client_id`) REFERENCES `oauth2_client` (`id`);
            ALTER TABLE `oauth2_accesstoken` ADD FOREIGN KEY (`client_id`) REFERENCES `oauth2_client` (`id`);
        """,
        )
    ]
